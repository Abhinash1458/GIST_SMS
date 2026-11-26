# app/services/approval.py

"""Registration approval business logic. Plain functions, no FastAPI code."""

import secrets
import string
from datetime import datetime, timezone

from sqlmodel import Session

from app.config import settings
from app.models import (
    Department,
    Registration,
    RegistrationStatus,
    Role,
    Student,
    StudentStatus,
    User,
)
from app.security import hash_password
from app.services.placement import (
    get_or_create_batch,
    pick_mentor_group,
    pick_section,
)
from app.services.roll_number import next_roll_number


TEMP_PASSWORD_LENGTH = 8


class ApprovalError(Exception):
    """Base class for approvals that cannot proceed."""


class AlreadyDecidedError(ApprovalError):
    """Raised when the registration is not pending."""

    def __init__(self, registration: Registration, message: str | None = None):
        self.registration = registration
        self.message = message or (
            "This registration has already been "
            f"{status_value(registration.status)}."
        )
        super().__init__(self.message)


class DepartmentMismatchError(ApprovalError):
    """Raised when the HOD does not belong to the registration's department."""

    def __init__(
        self, registration: Registration, message: str | None = None
    ):
        self.registration = registration
        self.message = message or (
            "This registration belongs to another department."
        )
        super().__init__(self.message)


def status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


def temporary_password(length: int = TEMP_PASSWORD_LENGTH) -> str:
    """Return a random alphanumeric password with at least one letter/digit."""
    characters = string.ascii_letters + string.digits
    value = [
        secrets.choice(string.ascii_letters),
        secrets.choice(string.digits),
    ]
    value.extend(secrets.choice(characters) for _ in range(length - 2))
    secrets.SystemRandom().shuffle(value)
    return "".join(value)


def approve_registration(
    session: Session,
    registration: Registration,
    hod_user: User,
) -> dict:
    """
    Approve a pending registration in one transaction.

    Returns a plain dict with the roll number, temporary password, section,
    mentor group and mentor name needed by the result page.
    """
    # Refresh so a stale object cannot be approved twice.
    session.refresh(registration)

    if status_value(registration.status) != RegistrationStatus.pending.value:
        raise AlreadyDecidedError(registration)

    if hod_user.department_id != registration.department_id:
        raise DepartmentMismatchError(registration)

    department = session.get(Department, registration.department_id)
    if not department:
        raise ValueError("The registration's department no longer exists.")

    admission_year = settings.ADMISSION_YEAR
    now = datetime.now(timezone.utc)

    try:
        batch = get_or_create_batch(session, department, admission_year)
        section = pick_section(session, batch)
        mentor_group = pick_mentor_group(session, section)
        roll_number = next_roll_number(session, department, admission_year)
        password = temporary_password()

        student_user = User(
            username=roll_number,
            full_name=registration.full_name,
            email=registration.email,
            password_hash=hash_password(password),
            role=Role.student,
            department_id=department.id,
            is_active=True,
            must_change_password=True,
            created_at=now,
        )
        session.add(student_user)
        session.flush()

        student = Student(
            user_id=student_user.id,
            roll_number=roll_number,
            full_name=registration.full_name,
            dob=registration.dob,
            gender=registration.gender,
            phone=registration.phone,
            city=registration.city,
            email=registration.email,
            parent_name=registration.parent_name,
            department_id=department.id,
            batch_id=batch.id,
            section_id=section.id,
            mentor_group_id=mentor_group.id if mentor_group else None,
            quota=registration.quota,
            admission_year=admission_year,
            status=StudentStatus.active,
            created_at=now,
        )
        session.add(student)
        session.flush()

        registration.status = RegistrationStatus.approved
        registration.hod_remarks = None
        registration.decided_at = now
        registration.decided_by_user_id = hod_user.id
        registration.student_id = student.id
        session.add(registration)

        # One commit for the entire promotion.
        session.commit()

    except Exception:
        session.rollback()
        raise

    mentor = (
        session.get(User, mentor_group.mentor_user_id)
        if mentor_group
        else None
    )

    serial_label = roll_number[-3:]
    return {
        "roll_number": roll_number,
        "temporary_password": password,
        "section_name": section.name,
        "mentor_group_name": mentor_group.name if mentor_group else None,
        "mentor_name": mentor.full_name if mentor and mentor.is_active else None,
        # Extra values used by the HOD result page.
        "username": roll_number,
        "department_code": department.code,
        "department_name": department.name,
        "year_part": f"{admission_year % 100:02d}",
        "branch_code": department.code,
        "serial": int(serial_label),
        "serial_label": serial_label,
        "batch_year": batch.start_year,
        "student_id": student.id,
        "registration_id": registration.id,
    }
