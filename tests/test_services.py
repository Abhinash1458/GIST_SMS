# tests/test_services.py

"""Quick, framework-free tests for the service functions."""

import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings
from app.models import (
    Batch,
    Department,
    MentorGroup,
    Registration,
    RegistrationStatus,
    Role,
    RollCounter,
    Section,
    Student,
    StudentStatus,
    User,
)
from app.security import hash_password
from app.services import (
    AlreadyDecidedError,
    DepartmentMismatchError,
    approve_registration,
    get_or_create_batch,
    next_roll_number,
    pick_mentor_group,
    pick_section,
)


NOW = datetime.now(timezone.utc)
YEAR = settings.ADMISSION_YEAR
DUMMY_PASSWORD_HASH = hash_password("Pass@12345")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)

        with Session(self.engine) as session:
            department = Department(
                code="CSE",
                name="Computer Science and Engineering",
                intake=120,
            )
            session.add(department)
            session.flush()

            hod = self.make_user(
                session,
                username="hod-cse",
                role=Role.hod,
                department_id=department.id,
                full_name="CSE HOD",
            )
            session.commit()
            self.department_id = department.id
            self.hod_id = hod.id

    def tearDown(self):
        # The in-memory database disappears with the engine.
        self.engine.dispose()

    # Helpers ---------------------------------------------------------

    def make_user(
        self, session, username, role, department_id, full_name="Test User"
    ):
        user = User(
            username=username,
            full_name=full_name,
            email=f"{username}@example.com",
            password_hash=DUMMY_PASSWORD_HASH,
            role=role,
            department_id=department_id,
            is_active=True,
            must_change_password=False,
            created_at=NOW,
        )
        session.add(user)
        session.flush()
        return user

    def make_registration(self, session, reference_no, full_name):
        registration = Registration(
            reference_no=reference_no,
            full_name=full_name,
            dob=date(2007, 5, 10),
            gender="Male",
            phone="9876543210",
            email=f"{reference_no.lower()}@example.com",
            parent_name="Test Parent",
            department_id=self.department_id,
            quota="Convener",
            entrance_rank=10,
            tenth_percent=88.5,
            inter_percent=91.25,
            status=RegistrationStatus.pending,
            submitted_at=NOW,
        )
        session.add(registration)
        session.flush()
        return registration

    def make_student(self, session, user, batch, section, group, roll_number):
        student = Student(
            user_id=user.id,
            roll_number=roll_number,
            full_name=user.full_name,
            dob=date(2007, 5, 10),
            gender="Male",
            phone="9876543210",
            email=user.email,
            parent_name="Test Parent",
            department_id=self.department_id,
            batch_id=batch.id,
            section_id=section.id,
            mentor_group_id=group.id if group else None,
            quota="Convener",
            admission_year=YEAR,
            status=StudentStatus.active,
            created_at=NOW,
        )
        session.add(student)
        session.flush()
        return student

    # Tests -----------------------------------------------------------

    def test_serials_go_001_002_003(self):
        with Session(self.engine) as session:
            department = session.get(Department, self.department_id)
            values = [
                next_roll_number(session, department, 2026) for _ in range(3)
            ]
            other_department = Department(
                code="IT", name="Information Technology", intake=120
            )
            session.add(other_department)
            session.flush()
            other_department_roll = next_roll_number(
                session, other_department, 2026
            )
            other_year_roll = next_roll_number(session, department, 2027)
            session.commit()

        self.assertEqual(
            values, ["26CSE001", "26CSE002", "26CSE003"]
        )
        # Serials are independent per department and per admission year.
        self.assertEqual(other_department_roll, "26IT001")
        self.assertEqual(other_year_roll, "27CSE001")

    def test_full_mentor_group_is_skipped(self):
        with Session(self.engine) as session:
            department = session.get(Department, self.department_id)
            batch = get_or_create_batch(session, department, YEAR)
            section = pick_section(session, batch)

            mentor = self.make_user(
                session, "mentor-cse", Role.mentor, self.department_id
            )
            full = MentorGroup(
                section_id=section.id,
                name="A-1",
                mentor_user_id=mentor.id,
                capacity=30,
            )
            spare = MentorGroup(
                section_id=section.id,
                name="A-2",
                mentor_user_id=mentor.id,
                capacity=30,
            )
            session.add(full)
            session.add(spare)
            session.flush()

            for index in range(30):
                user = self.make_user(
                    session, f"full-{index}", Role.student, self.department_id
                )
                self.make_student(
                    session, user, batch, section, full, f"FULL{index:03d}"
                )
            session.commit()

            picked = pick_mentor_group(session, section)
            self.assertIsNotNone(picked)
            self.assertEqual(picked.id, spare.id)

            # Once the spare group is full too, nothing is available.
            for index in range(30):
                user = self.make_user(
                    session, f"spare-{index}", Role.student, self.department_id
                )
                self.make_student(
                    session, user, batch, section, spare, f"SPARE{index:03d}"
                )
            session.commit()

            self.assertIsNone(pick_mentor_group(session, section))

    def test_second_approve_fails(self):
        with Session(self.engine) as session:
            registration = self.make_registration(
                session, "REG-TEST-1", "First Student"
            )
            hod = session.get(User, self.hod_id)
            session.commit()

            result = approve_registration(session, registration, hod)

            self.assertEqual(
                result["roll_number"], f"{YEAR % 100:02d}CSE001"
            )
            self.assertEqual(len(result["temporary_password"]), 8)
            self.assertTrue(result["section_name"])

            with self.assertRaises(AlreadyDecidedError):
                approve_registration(session, registration, hod)

            count = session.exec(select(func.count(Student.id))).one()
            self.assertEqual(count, 1)

    def test_two_approvals_increment_roll_number(self):
        with Session(self.engine) as session:
            first = self.make_registration(
                session, "REG-TEST-2", "Second Student"
            )
            second = self.make_registration(
                session, "REG-TEST-3", "Third Student"
            )
            hod = session.get(User, self.hod_id)
            session.commit()

            first_result = approve_registration(session, first, hod)
            second_result = approve_registration(session, second, hod)

            self.assertEqual(
                second_result["roll_number"][-3:],
                f"{int(first_result['roll_number'][-3:]) + 1:03d}",
            )

    def test_three_approvals_give_001_002_003(self):
        with Session(self.engine) as session:
            hod = session.get(User, self.hod_id)
            registrations = [
                self.make_registration(
                    session, f"REG-THREE-{index}", f"Student {index}"
                )
                for index in range(3)
            ]
            session.commit()

            roll_numbers = [
                approve_registration(session, registration, hod)["roll_number"]
                for registration in registrations
            ]

        prefix = f"{YEAR % 100:02d}CSE"
        self.assertEqual(
            roll_numbers,
            [f"{prefix}001", f"{prefix}002", f"{prefix}003"],
        )

    def test_other_department_hod_is_refused(self):
        with Session(self.engine) as session:
            other_department = Department(
                code="IT", name="Information Technology", intake=120
            )
            session.add(other_department)
            session.flush()
            other_hod = self.make_user(
                session,
                "hod-it",
                Role.hod,
                other_department.id,
                "IT HOD",
            )
            registration = self.make_registration(
                session, "REG-OTHER-DEPT", "Wrong Department"
            )
            session.commit()

            with self.assertRaises(DepartmentMismatchError):
                approve_registration(session, registration, other_hod)

            self.assertEqual(
                registration.status, RegistrationStatus.pending
            )

    def test_failed_approval_rolls_back_everything(self):
        with Session(self.engine) as session:
            registration = self.make_registration(
                session, "REG-ROLLBACK", "Rollback Student"
            )
            registration_id = registration.id
            # Force a failure after the counter has been incremented.
            self.make_user(
                session,
                f"{YEAR % 100:02d}CSE001",
                Role.student,
                self.department_id,
            )
            hod = session.get(User, self.hod_id)
            session.commit()

            with self.assertRaises(IntegrityError):
                approve_registration(session, registration, hod)

            counter = session.exec(
                select(RollCounter).where(
                    RollCounter.department_id == self.department_id,
                    RollCounter.admission_year == YEAR,
                )
            ).first()
            self.assertIsNone(counter)
            self.assertEqual(
                session.exec(select(func.count(Student.id))).one(), 0
            )
            self.assertEqual(
                session.exec(
                    select(Registration.status).where(
                        Registration.id == registration_id
                    )
                ).one(),
                RegistrationStatus.pending,
            )


if __name__ == "__main__":
    unittest.main()
