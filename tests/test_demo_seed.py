"""Tests for the deterministic demo dataset."""

import unittest
from datetime import date

from sqlalchemy import func
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.models import (
    Batch,
    Department,
    MentorGroup,
    Notice,
    Registration,
    RegistrationStatus,
    Section,
    Student,
    Subject,
    TeachingAssignment,
    User,
)
from app.services.roll_number import next_roll_number
from scripts.seed import academic_position, seed_demo_data


class DemoSeedTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.result = seed_demo_data(
            self.engine,
            today=date(2026, 11, 26),
        )

    def tearDown(self):
        self.engine.dispose()

    def test_seed_creates_expected_record_counts(self):
        counts = self.result["counts"]
        self.assertEqual(counts["Users"], 549)
        self.assertEqual(counts["Departments"], 5)
        self.assertEqual(counts["Batches"], 20)
        self.assertEqual(counts["Sections"], 40)
        self.assertEqual(counts["Mentor groups"], 40)
        self.assertEqual(counts["Students"], 500)
        self.assertEqual(counts["Subjects"], 120)
        self.assertEqual(counts["Teaching assignments"], 240)
        self.assertEqual(counts["Registrations"], 40)
        self.assertEqual(counts["Notices"], 3)

    def test_each_department_has_registration_work(self):
        with Session(self.engine) as session:
            departments = session.exec(select(Department)).all()
            for department in departments:
                registrations = session.exec(
                    select(Registration).where(
                        Registration.department_id == department.id
                    )
                ).all()
                statuses = [item.status for item in registrations]
                self.assertEqual(
                    statuses.count(RegistrationStatus.pending),
                    6,
                )
                self.assertEqual(
                    statuses.count(RegistrationStatus.correction),
                    1,
                )
                self.assertEqual(
                    statuses.count(RegistrationStatus.rejected),
                    1,
                )

    def test_every_section_has_one_mentor_group_and_at_most_30_students(self):
        with Session(self.engine) as session:
            sections = session.exec(select(Section)).all()
            self.assertEqual(len(sections), 40)
            for section in sections:
                groups = session.exec(
                    select(MentorGroup).where(
                        MentorGroup.section_id == section.id
                    )
                ).all()
                self.assertEqual(len(groups), 1)
                student_count = len(
                    session.exec(
                        select(Student).where(Student.section_id == section.id)
                    ).all()
                )
                self.assertLessEqual(student_count, groups[0].capacity)
                self.assertLessEqual(student_count, 30)

    def test_roll_counters_leave_the_next_real_serial_available(self):
        with Session(self.engine) as session:
            department = session.exec(
                select(Department).where(Department.code == "CSE")
            ).first()
            next_roll = next_roll_number(session, department, 2026)
            self.assertEqual(next_roll, "26CSE026")

    def test_section_positions_match_todays_academic_date(self):
        with Session(self.engine) as session:
            for batch in session.exec(select(Batch)).all():
                expected = academic_position(batch.start_year, date(2026, 11, 26))
                sections = session.exec(
                    select(Section).where(Section.batch_id == batch.id)
                ).all()
                for section in sections:
                    self.assertEqual(
                        (section.current_year, section.current_semester),
                        expected,
                    )

    def test_academic_position_handles_semester_boundaries(self):
        self.assertEqual(
            academic_position(2026, date(2027, 1, 15)),
            (1, 2),
        )
        self.assertEqual(
            academic_position(2026, date(2027, 7, 15)),
            (2, 3),
        )
        self.assertEqual(
            academic_position(2026, date(2026, 6, 15)),
            (1, 1),
        )

    def test_teaching_assignments_cover_both_sections_for_each_subject(self):
        with Session(self.engine) as session:
            for subject in session.exec(select(Subject)).all():
                assignments = session.exec(
                    select(TeachingAssignment).where(
                        TeachingAssignment.subject_id == subject.id
                    )
                ).all()
                self.assertEqual(len(assignments), 2)
                assignment_batches = set()
                for assignment in assignments:
                    section = session.get(Section, assignment.section_id)
                    assignment_batches.add(section.batch_id)
                self.assertEqual(len(assignment_batches), 1)

    def test_printed_student_login_is_ravi_kumar(self):
        with Session(self.engine) as session:
            student = session.exec(
                select(Student).where(Student.roll_number == "26CSE001")
            ).first()
            self.assertEqual(student.full_name, "Ravi Kumar")
            self.assertEqual(
                self.result["demo_logins"]["student"]["username"],
                "26CSE001",
            )

    def test_running_the_seed_again_resets_and_reproduces_the_data(self):
        with Session(self.engine) as session:
            first_snapshot = [
                (item.roll_number, item.full_name, item.phone, item.city)
                for item in session.exec(
                    select(Student).order_by(Student.roll_number)
                ).all()
            ]

        second_result = seed_demo_data(
            self.engine,
            today=date(2026, 11, 26),
        )

        with Session(self.engine) as session:
            second_snapshot = [
                (item.roll_number, item.full_name, item.phone, item.city)
                for item in session.exec(
                    select(Student).order_by(Student.roll_number)
                ).all()
            ]
            self.assertEqual(
                session.exec(select(func.count(User.id))).one(),
                549,
            )

        self.assertEqual(first_snapshot, second_snapshot)
        self.assertEqual(second_result["counts"], self.result["counts"])


if __name__ == "__main__":
    unittest.main()
