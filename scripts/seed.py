"""Load a deterministic, realistic demo dataset for GIST SMS.

Run from the project root with::

    python -m scripts.seed

Every run resets the configured database to an empty schema before loading the
same deterministic academic data. The fixed passwords are for demonstrations
only and must never be assigned to real users.
"""

from __future__ import annotations

import random
import sys
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from faker import Faker
from sqlalchemy import func
from sqlalchemy.exc import SAWarning
from sqlmodel import Session, SQLModel, select

# Add project root to Python path when this file is run directly.
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.database import engine
from app.models import (
    Attendance,
    Batch,
    Department,
    Exam,
    ExamSchedule,
    HallTicket,
    LeaveRequest,
    Mark,
    MentorGroup,
    Notice,
    Registration,
    RegistrationStatus,
    Role,
    RollCounter,
    Section,
    Student,
    StudentStatus,
    Subject,
    TeachingAssignment,
    User,
)
from app.security import hash_password
from app.services.roll_number import next_roll_number


DEMO_SEED = 20261126
ADMISSION_YEARS = (2023, 2024, 2025, 2026)
DEMO_CREATED_AT = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)

DEMO_PASSWORDS = {
    "management": "Admin@123",
    "hod": "Hod@123",
    "mentor": "Mentor@123",
    "trainer": "Trainer@123",
    "student": "Student@123",
}

DEPARTMENT_SPECS = (
    ("CSE", "Computer Science and Engineering"),
    ("ECE", "Electronics and Communication Engineering"),
    ("EEE", "Electrical and Electronics Engineering"),
    ("MECH", "Mechanical Engineering"),
    ("CIVIL", "Civil Engineering"),
)

HOD_NAMES = {
    "CSE": "Dr. Anjali Sharma",
    "ECE": "Dr. Rajesh Iyer",
    "EEE": "Dr. Vikram Reddy",
    "MECH": "Dr. Meera Nair",
    "CIVIL": "Dr. Arjun Patel",
}

TRAINER_NAMES = (
    "Prof. Arjun Mehta",
    "Prof. Kavya Nair",
    "Prof. Rohan Desai",
)

SUBJECT_NAMES = {
    "CSE": (
        "Programming Fundamentals",
        "Data Structures and Algorithms",
        "Digital Logic Design",
        "Database Management Systems",
        "Computer Networks",
        "Operating Systems",
    ),
    "ECE": (
        "Basic Electrical Engineering",
        "Network Analysis",
        "Analog Circuits",
        "Digital Signal Processing",
        "Microcontrollers",
        "VLSI Design",
    ),
    "EEE": (
        "Engineering Mathematics",
        "Electrical Machines",
        "Power Systems",
        "Control Systems",
        "High Voltage Engineering",
        "Renewable Energy Systems",
    ),
    "MECH": (
        "Engineering Graphics",
        "Thermodynamics",
        "Fluid Mechanics",
        "Manufacturing Processes",
        "Machine Design",
        "Heat Transfer",
    ),
    "CIVIL": (
        "Engineering Survey",
        "Structural Mechanics",
        "Concrete Technology",
        "Transportation Engineering",
        "Geotechnical Engineering",
        "Water Resources Engineering",
    ),
}

SUMMARY_MODELS = (
    ("Users", User),
    ("Departments", Department),
    ("Batches", Batch),
    ("Sections", Section),
    ("Mentor groups", MentorGroup),
    ("Students", Student),
    ("Subjects", Subject),
    ("Teaching assignments", TeachingAssignment),
    ("Roll counters", RollCounter),
    ("Registrations", Registration),
    ("Notices", Notice),
    ("Attendance records", Attendance),
    ("Marks", Mark),
    ("Exams", Exam),
    ("Exam schedules", ExamSchedule),
    ("Hall tickets", HallTicket),
    ("Leave requests", LeaveRequest),
)


def academic_position(admission_year: int, today: date) -> tuple[int, int]:
    """Return the current year and semester for an admission cohort."""
    if today < date(admission_year, 7, 1):
        return 1, 1

    elapsed_years = today.year - admission_year
    if today.month >= 7:
        current_year = elapsed_years + 1
        current_semester = 2 * current_year - 1
    else:
        current_year = max(1, elapsed_years)
        current_semester = 2 * current_year

    return min(current_year, 4), min(current_semester, 8)


def indian_phone_number(rng: random.Random) -> str:
    """Generate a valid-looking Indian 10-digit mobile number."""
    first_digit = rng.choice(("6", "7", "8", "9"))
    remaining = "".join(str(rng.randint(0, 9)) for _ in range(9))
    return f"{first_digit}{remaining}"


def add_user(
    session: Session,
    *,
    username: str,
    full_name: str,
    email: str,
    password_hash: str,
    role: Role,
    department_id: int | None = None,
    created_at: datetime = DEMO_CREATED_AT,
) -> User:
    user = User(
        username=username,
        full_name=full_name,
        email=email,
        password_hash=password_hash,
        role=role,
        department_id=department_id,
        is_active=True,
        must_change_password=False,
        created_at=created_at,
    )
    session.add(user)
    session.flush()
    return user


def reset_database(target_engine) -> None:
    """Remove every application table and recreate an empty schema."""
    # User.department_id and Department.hod_user_id form a deliberate,
    # nullable cycle. SQLite can drop this cycle safely; suppress SQLAlchemy's
    # backend-specific ALTER warning so the classroom command stays clean.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Can't sort tables for DROP.*",
            category=SAWarning,
        )
        SQLModel.metadata.drop_all(target_engine)
    SQLModel.metadata.create_all(target_engine)


def seed_demo_data(target_engine=None, today: date | None = None) -> dict:
    """Reset and populate the demo database, returning counts and logins."""
    target_engine = target_engine or engine
    today = today or date.today()

    reset_database(target_engine)

    fake = Faker("en_IN")
    fake.seed_instance(DEMO_SEED)
    rng = random.Random(DEMO_SEED)

    password_hashes = {
        role: hash_password(password)
        for role, password in DEMO_PASSWORDS.items()
    }

    demo_logins = {
        "management": {
            "username": "management@college.edu",
            "password": DEMO_PASSWORDS["management"],
        },
        "hod": {
            "username": "hod.cse@college.edu",
            "password": DEMO_PASSWORDS["hod"],
        },
        "mentor": {
            "username": "mentor.cse.2026a@college.edu",
            "password": DEMO_PASSWORDS["mentor"],
        },
        "trainer": {
            "username": "trainer1@college.edu",
            "password": DEMO_PASSWORDS["trainer"],
        },
        "student": {
            "username": "",
            "password": DEMO_PASSWORDS["student"],
        },
    }

    with Session(target_engine) as session:
        try:
            management = add_user(
                session,
                username="management@college.edu",
                full_name="Anil Kumar",
                email="management@college.edu",
                password_hash=password_hashes["management"],
                role=Role.management,
            )

            departments: dict[str, Department] = {}
            hods: dict[str, User] = {}
            trainers = []
            for index, full_name in enumerate(TRAINER_NAMES, start=1):
                trainer = add_user(
                    session,
                    username=f"trainer{index}@college.edu",
                    full_name=full_name,
                    email=f"trainer{index}@college.edu",
                    password_hash=password_hashes["trainer"],
                    role=Role.trainer,
                )
                trainers.append(trainer)

            for code, name in DEPARTMENT_SPECS:
                department = Department(
                    code=code,
                    name=name,
                    intake=120,
                )
                session.add(department)
                session.flush()
                departments[code] = department

                hod = add_user(
                    session,
                    username=f"hod.{code.lower()}@college.edu",
                    full_name=HOD_NAMES[code],
                    email=f"hod.{code.lower()}@college.edu",
                    password_hash=password_hashes["hod"],
                    role=Role.hod,
                    department_id=department.id,
                )
                hods[code] = hod
                department.hod_user_id = hod.id
                session.add(department)

            section_map: dict[tuple[str, int, str], dict] = {}
            for code, _ in DEPARTMENT_SPECS:
                department = departments[code]
                for admission_year in ADMISSION_YEARS:
                    batch = Batch(
                        department_id=department.id,
                        start_year=admission_year,
                        end_year=admission_year + 4,
                    )
                    session.add(batch)
                    session.flush()

                    for section_name, student_target in (("A", 13), ("B", 12)):
                        current_year, current_semester = academic_position(
                            admission_year,
                            today,
                        )
                        section = Section(
                            batch_id=batch.id,
                            name=section_name,
                            current_year=current_year,
                            current_semester=current_semester,
                            capacity=60,
                        )
                        session.add(section)
                        session.flush()

                        mentor_email = (
                            f"mentor.{code.lower()}.{admission_year}"
                            f"{section_name.lower()}@college.edu"
                        )
                        mentor = add_user(
                            session,
                            username=mentor_email,
                            full_name=fake.name(),
                            email=mentor_email,
                            password_hash=password_hashes["mentor"],
                            role=Role.mentor,
                            department_id=department.id,
                        )
                        mentor_group = MentorGroup(
                            section_id=section.id,
                            name=f"{code} {admission_year} {section_name}",
                            mentor_user_id=mentor.id,
                            capacity=30,
                        )
                        session.add(mentor_group)
                        session.flush()

                        section_map[(code, admission_year, section_name)] = {
                            "batch": batch,
                            "section": section,
                            "mentor": mentor,
                            "group": mentor_group,
                            "student_target": student_target,
                        }

            for code, _ in DEPARTMENT_SPECS:
                department = departments[code]
                for admission_year in ADMISSION_YEARS:
                    for section_name in ("A", "B"):
                        section_data = section_map[
                            (code, admission_year, section_name)
                        ]
                        section = section_data["section"]
                        mentor_group = section_data["group"]

                        for student_index in range(
                            section_data["student_target"]
                        ):
                            roll_number = next_roll_number(
                                session,
                                department,
                                admission_year,
                            )
                            is_special_demo_student = (
                                code == "CSE"
                                and admission_year == 2026
                                and section_name == "A"
                                and student_index == 0
                            )

                            if is_special_demo_student:
                                full_name = "Ravi Kumar"
                                gender = "Male"
                                parent_name = "Ramesh Kumar"
                                city = "Bengaluru"
                                phone = "9876543210"
                            else:
                                gender = rng.choice(("Male", "Female"))
                                full_name = (
                                    fake.name_male()
                                    if gender == "Male"
                                    else fake.name_female()
                                )
                                parent_name = (
                                    fake.name_male()
                                    if rng.choice((True, False))
                                    else fake.name_female()
                                )
                                city = fake.city()
                                phone = indian_phone_number(rng)

                            birth_year = admission_year - 18 - rng.choice((0, 1))
                            birth_date = date(
                                birth_year,
                                rng.randint(1, 12),
                                rng.randint(1, 28),
                            )
                            quota = rng.choice(
                                ("General", "BC", "SC", "ST", "EWS")
                            )
                            student_email = f"{roll_number.lower()}@college.edu"

                            student_user = add_user(
                                session,
                                username=roll_number,
                                full_name=full_name,
                                email=student_email,
                                password_hash=password_hashes["student"],
                                role=Role.student,
                                department_id=department.id,
                            )
                            student = Student(
                                user_id=student_user.id,
                                roll_number=roll_number,
                                full_name=full_name,
                                dob=birth_date,
                                gender=gender,
                                phone=phone,
                                city=city,
                                email=student_email,
                                parent_name=parent_name,
                                department_id=department.id,
                                batch_id=section_data["batch"].id,
                                section_id=section.id,
                                mentor_group_id=mentor_group.id,
                                quota=quota,
                                admission_year=admission_year,
                                status=StudentStatus.active,
                                created_at=DEMO_CREATED_AT,
                            )
                            session.add(student)
                            session.flush()

                            if is_special_demo_student:
                                demo_logins["student"]["username"] = roll_number

            for code, _ in DEPARTMENT_SPECS:
                department = departments[code]
                for admission_year in ADMISSION_YEARS:
                    batch_year, batch_semester = academic_position(
                        admission_year,
                        today,
                    )
                    for subject_index, subject_name in enumerate(
                        SUBJECT_NAMES[code]
                    ):
                        subject = Subject(
                            code=(
                                f"{code}{admission_year % 100:02d}"
                                f"{subject_index + 1:02d}"
                            ),
                            name=subject_name,
                            department_id=department.id,
                            year=batch_year,
                            semester=batch_semester,
                            credits=3 if subject_index % 2 == 0 else 4,
                        )
                        session.add(subject)
                        session.flush()

                        for section_name in ("A", "B"):
                            section_data = section_map[
                                (code, admission_year, section_name)
                            ]
                            if subject_index < 3:
                                teacher = trainers[subject_index]
                            elif subject_index == 4:
                                teacher = hods[code]
                            else:
                                teacher = section_data["mentor"]

                            assignment = TeachingAssignment(
                                subject_id=subject.id,
                                section_id=section_data["section"].id,
                                teacher_user_id=teacher.id,
                            )
                            session.add(assignment)

            registration_number = 0
            for code, _ in DEPARTMENT_SPECS:
                department = departments[code]
                statuses = (
                    RegistrationStatus.pending,
                    RegistrationStatus.pending,
                    RegistrationStatus.pending,
                    RegistrationStatus.pending,
                    RegistrationStatus.pending,
                    RegistrationStatus.pending,
                    RegistrationStatus.correction,
                    RegistrationStatus.rejected,
                )
                for local_index, status in enumerate(statuses, start=1):
                    registration_number += 1
                    gender = rng.choice(("Male", "Female"))
                    full_name = (
                        fake.name_male()
                        if gender == "Male"
                        else fake.name_female()
                    )
                    parent_name = (
                        fake.name_male()
                        if rng.choice((True, False))
                        else fake.name_female()
                    )
                    submitted_at = DEMO_CREATED_AT - timedelta(
                        days=registration_number,
                        hours=local_index,
                    )
                    decided_at = (
                        submitted_at + timedelta(hours=2)
                        if status != RegistrationStatus.pending
                        else None
                    )
                    registration = Registration(
                        reference_no=(
                            f"REG-{settings.ADMISSION_YEAR}-"
                            f"{registration_number:05d}"
                        ),
                        full_name=full_name,
                        dob=date(
                            2008,
                            rng.randint(1, 12),
                            rng.randint(1, 28),
                        ),
                        gender=gender,
                        phone=indian_phone_number(rng),
                        city=fake.city(),
                        email=f"applicant{registration_number}@college.edu",
                        parent_name=parent_name,
                        department_id=department.id,
                        quota=rng.choice(
                            ("General", "BC", "SC", "ST", "EWS")
                        ),
                        entrance_rank=1000 + registration_number * 17,
                        tenth_percent=round(rng.uniform(72, 98), 2),
                        inter_percent=round(rng.uniform(70, 99), 2),
                        status=status,
                        hod_remarks=(
                            "Please correct the parent name and attach the latest "
                            "marks memo."
                            if status == RegistrationStatus.correction
                            else (
                                "The entrance score could not be verified from "
                                "the uploaded documents."
                                if status == RegistrationStatus.rejected
                                else None
                            )
                        ),
                        submitted_at=submitted_at,
                        decided_at=decided_at,
                        decided_by_user_id=(
                            hods[code].id
                            if status != RegistrationStatus.pending
                            else None
                        ),
                    )
                    session.add(registration)

            notice_specs = (
                (
                    "Orientation programme for the 2026 batch",
                    "The induction programme will begin at 9:30 AM in the main "
                    "auditorium. Students should carry their college identity card.",
                    "students",
                    Role.student,
                    DEMO_CREATED_AT + timedelta(days=1),
                ),
                (
                    "Department faculty review meeting",
                    "HODs should review pending registrations and mentor-group "
                    "coverage before the next academic review meeting.",
                    "staff",
                    Role.hod,
                    DEMO_CREATED_AT + timedelta(days=3),
                ),
                (
                    "Library week and mentor meetup",
                    "Library week begins on Monday. Mentors are requested to "
                    "schedule a short student orientation meeting this week.",
                    "all",
                    None,
                    DEMO_CREATED_AT + timedelta(days=5),
                ),
            )
            for title, body, audience, role, created_at in notice_specs:
                session.add(
                    Notice(
                        title=title,
                        body=body,
                        audience=audience,
                        role=role,
                        created_by_user_id=management.id,
                        created_at=created_at,
                    )
                )

            session.commit()
            counts = collect_counts(session)

        except Exception:
            session.rollback()
            raise

    return {
        "counts": counts,
        "demo_logins": demo_logins,
        "database_url": settings.DATABASE_URL,
    }


def collect_counts(session: Session) -> dict[str, int]:
    """Count rows in every application table."""
    return {
        label: session.exec(select(func.count(model.id))).one()
        for label, model in SUMMARY_MODELS
    }


def print_summary(result: dict) -> None:
    counts = result["counts"]
    logins = result["demo_logins"]

    print("=" * 72)
    print("GIST SMS demo data is ready")
    print(f"Database: {result['database_url']}")
    print("=" * 72)
    print("Demo logins (one per role):")
    print(
        f"  Management      {logins['management']['username']}  /  "
        f"{logins['management']['password']}"
    )
    print(
        f"  HOD             {logins['hod']['username']}  /  "
        f"{logins['hod']['password']}"
    )
    print(
        f"  Mentor          {logins['mentor']['username']}  /  "
        f"{logins['mentor']['password']}"
    )
    print(
        f"  External Trainer {logins['trainer']['username']}  /  "
        f"{logins['trainer']['password']}"
    )
    print(
        f"  Student         {logins['student']['username']}  /  "
        f"{logins['student']['password']}"
    )

    print("\nRecord counts:")
    for label, count in counts.items():
        print(f"  {label:<24} {count:>6}")

    print("\nIMPORTANT: These fixed passwords are for demonstration only.")
    print("Never use them for real users or a production deployment.")


def main() -> None:
    print("Resetting the configured database before loading demo data...")
    result = seed_demo_data()
    print_summary(result)


if __name__ == "__main__":
    main()
