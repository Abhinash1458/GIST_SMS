"""Database-backed data for the five role dashboards.

The dashboard routes should not contain hand-written totals. Every figure in
this module is queried from the application's database so the demo and the
real application follow the same code path.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlmodel import Session, select

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


def _count(session: Session, model, *conditions) -> int:
    statement = select(func.count(model.id))
    if conditions:
        statement = statement.where(*conditions)
    return session.exec(statement).one()


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def management_dashboard_data(session: Session) -> dict:
    """Return management metrics across every department."""
    departments = session.exec(
        select(Department).order_by(Department.code)
    ).all()

    total_students = _count(session, Student)
    total_departments = _count(session, Department)
    pending_registrations = _count(
        session,
        Registration,
        Registration.status == RegistrationStatus.pending,
    )

    year_rows = session.execute(
        select(Student.admission_year, func.count(Student.id))
        .group_by(Student.admission_year)
        .order_by(Student.admission_year)
    ).all()
    students_by_year = [
        {"year": int(year), "count": int(count)}
        for year, count in year_rows
    ]
    year_count = len(students_by_year)
    average_students_per_year = (
        round(total_students / year_count, 1) if year_count else 0
    )

    department_rows = []
    for department in departments:
        student_count = _count(
            session,
            Student,
            Student.department_id == department.id,
        )
        pending_count = _count(
            session,
            Registration,
            Registration.department_id == department.id,
            Registration.status == RegistrationStatus.pending,
        )
        hod = (
            session.get(User, department.hod_user_id)
            if department.hod_user_id
            else None
        )
        department_rows.append(
            {
                "department": department,
                "hod_name": hod.full_name if hod else "Not assigned",
                "student_count": student_count,
                "pending_count": pending_count,
            }
        )

    maximum_students = max(
        (row["student_count"] for row in department_rows),
        default=0,
    )
    for row in department_rows:
        row["chart_percent"] = (
            round(row["student_count"] / maximum_students * 100, 1)
            if maximum_students
            else 0
        )

    return {
        "total_students": total_students,
        "students_per_year": average_students_per_year,
        "year_count": year_count,
        "students_by_year": students_by_year,
        "total_departments": total_departments,
        "pending_registrations": pending_registrations,
        "department_rows": department_rows,
    }


def hod_dashboard_data(session: Session, department_id: int | None) -> dict:
    """Return HOD metrics scoped strictly to one department."""
    if not department_id:
        return {
            "student_count": 0,
            "section_count": 0,
            "mentor_group_count": 0,
            "pending_count": 0,
            "section_rows": [],
            "unassigned_sections": [],
        }

    student_count = _count(
        session,
        Student,
        Student.department_id == department_id,
    )
    pending_count = _count(
        session,
        Registration,
        Registration.department_id == department_id,
        Registration.status == RegistrationStatus.pending,
    )

    sections = session.exec(
        select(Section)
        .join(Batch, Section.batch_id == Batch.id)
        .where(Batch.department_id == department_id)
        .order_by(Batch.start_year, Section.name)
    ).all()

    mentor_group_count = session.exec(
        select(func.count(MentorGroup.id))
        .join(Section, MentorGroup.section_id == Section.id)
        .join(Batch, Section.batch_id == Batch.id)
        .where(Batch.department_id == department_id)
    ).one()

    section_rows = []
    unassigned_sections = []
    for section in sections:
        batch = session.get(Batch, section.batch_id)
        group = session.exec(
            select(MentorGroup)
            .where(MentorGroup.section_id == section.id)
            .order_by(MentorGroup.name)
        ).first()
        mentor = (
            session.get(User, group.mentor_user_id)
            if group and group.mentor_user_id
            else None
        )
        section_student_count = _count(
            session,
            Student,
            Student.section_id == section.id,
        )
        unassigned_count = _count(
            session,
            Student,
            Student.section_id == section.id,
            Student.mentor_group_id.is_(None),
        )

        row = {
            "section": section,
            "batch": batch,
            "student_count": section_student_count,
            "mentor_group": group,
            "mentor_name": mentor.full_name if mentor else "Not assigned",
            "unassigned_count": unassigned_count,
        }
        section_rows.append(row)
        if unassigned_count:
            unassigned_sections.append(row)

    return {
        "student_count": student_count,
        "section_count": len(sections),
        "mentor_group_count": mentor_group_count,
        "pending_count": pending_count,
        "section_rows": section_rows,
        "unassigned_sections": unassigned_sections,
    }


def mentor_dashboard_data(session: Session, mentor: User) -> dict:
    """Return the mentor's group and its students."""
    group = session.exec(
        select(MentorGroup)
        .where(MentorGroup.mentor_user_id == mentor.id)
        .order_by(MentorGroup.name)
    ).first()

    if not group:
        return {
            "group": None,
            "section": None,
            "batch": None,
            "students": [],
            "student_count": 0,
        }

    section = session.get(Section, group.section_id)
    batch = session.get(Batch, section.batch_id) if section else None
    students = session.exec(
        select(Student)
        .where(Student.mentor_group_id == group.id)
        .order_by(Student.roll_number)
    ).all()

    return {
        "group": group,
        "section": section,
        "batch": batch,
        "students": students,
        "student_count": len(students),
    }


def trainer_dashboard_data(session: Session, trainer: User) -> dict:
    """Return the external trainer's teaching assignments."""
    assignments = session.exec(
        select(TeachingAssignment)
        .where(TeachingAssignment.teacher_user_id == trainer.id)
        .order_by(TeachingAssignment.subject_id, TeachingAssignment.section_id)
    ).all()

    rows = []
    for assignment in assignments:
        subject = session.get(Subject, assignment.subject_id)
        section = session.get(Section, assignment.section_id)
        batch = session.get(Batch, section.batch_id) if section else None
        department = (
            session.get(Department, section_department_id(section, batch))
            if section and batch
            else None
        )
        student_count = (
            _count(session, Student, Student.section_id == section.id)
            if section
            else 0
        )
        rows.append(
            {
                "assignment": assignment,
                "subject": subject,
                "section": section,
                "batch": batch,
                "department": department,
                "student_count": student_count,
            }
        )

    unique_section_ids = {
        row["section"].id
        for row in rows
        if row["section"] is not None
    }
    total_students = sum(
        _count(session, Student, Student.section_id == section_id)
        for section_id in unique_section_ids
    )

    return {
        "assignments": rows,
        "assignment_count": len(rows),
        "total_students": total_students,
    }


def section_department_id(section: Section, batch: Batch) -> int | None:
    """Return a section's department through its batch."""
    return batch.department_id if section and batch else None


def student_dashboard_data(session: Session, student_user: User) -> dict:
    """Return one student's academic profile, mentor and latest notice."""
    student = session.exec(
        select(Student).where(Student.user_id == student_user.id)
    ).first()

    if not student:
        return {
            "student": None,
            "department": None,
            "section": None,
            "batch": None,
            "mentor_group": None,
            "mentor": None,
            "latest_notice": None,
            "first_name": student_user.full_name.split()[0],
        }

    department = session.get(Department, student.department_id)
    section = session.get(Section, student.section_id)
    batch = session.get(Batch, student.batch_id)
    mentor_group = (
        session.get(MentorGroup, student.mentor_group_id)
        if student.mentor_group_id
        else None
    )
    mentor = (
        session.get(User, mentor_group.mentor_user_id)
        if mentor_group and mentor_group.mentor_user_id
        else None
    )

    notices = session.exec(
        select(Notice).order_by(Notice.created_at.desc())
    ).all()
    latest_notice = next(
        (
            notice
            for notice in notices
            if _notice_applies_to_student(notice, student)
        ),
        None,
    )

    return {
        "student": student,
        "department": department,
        "section": section,
        "batch": batch,
        "mentor_group": mentor_group,
        "mentor": mentor,
        "latest_notice": latest_notice,
        "first_name": student.full_name.split()[0],
        "status": _enum_value(student.status).title(),
    }


def _notice_applies_to_student(notice: Notice, student: Student) -> bool:
    notice_role = _enum_value(notice.role) if notice.role is not None else None
    if notice_role and notice_role != "student":
        return False

    audience = notice.audience.lower()
    if audience not in {"all", "students", "student"}:
        return False

    if notice.department_id and notice.department_id != student.department_id:
        return False
    if notice.section_id and notice.section_id != student.section_id:
        return False
    return True
