# app/services/placement.py

"""Batch/section/mentor-group placement. Plain functions, no FastAPI code."""

from string import ascii_uppercase

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Batch, Department, MentorGroup, Section, Student


DEFAULT_SECTION_CAPACITY = 60


def get_or_create_batch(
    session: Session, department: Department, admission_year: int
) -> Batch:
    batch = session.exec(
        select(Batch).where(
            Batch.department_id == department.id,
            Batch.start_year == admission_year,
        )
    ).first()

    if batch:
        return batch

    batch = Batch(
        department_id=department.id,
        start_year=admission_year,
        end_year=admission_year + 4,
    )
    session.add(batch)
    session.flush()
    return batch


def _student_count(session: Session, column, value: int) -> int:
    return session.exec(
        select(func.count(Student.id)).where(column == value)
    ).one()


def _next_section_name(sections: list[Section]) -> str:
    used = {section.name for section in sections}
    for letter in ascii_uppercase:
        if letter not in used:
            return letter
    return f"S{len(sections) + 1}"


def pick_section(session: Session, batch: Batch) -> Section:
    """Pick the least-populated section with space, or create the next one."""
    sections = session.exec(
        select(Section).where(Section.batch_id == batch.id).order_by(Section.name)
    ).all()

    chosen = None
    chosen_count = 0

    for section in sections:
        count = _student_count(session, Student.section_id, section.id)
        if count < section.capacity and (chosen is None or count < chosen_count):
            chosen, chosen_count = section, count

    if chosen:
        return chosen

    section = Section(
        batch_id=batch.id,
        name=_next_section_name(sections),
        current_year=1,
        current_semester=1,
        capacity=DEFAULT_SECTION_CAPACITY,
    )
    session.add(section)
    session.flush()
    return section


def pick_mentor_group(
    session: Session, section: Section
) -> MentorGroup | None:
    """
    Pick the least-populated mentor group in this section with space.

    Returns None when every group already reaches its configured capacity, so
    the caller can warn the HOD to create a new mentor group for the section.
    """
    groups = session.exec(
        select(MentorGroup)
        .where(MentorGroup.section_id == section.id)
        .order_by(MentorGroup.name)
    ).all()

    chosen = None
    chosen_count = 0

    for group in groups:
        count = _student_count(session, Student.mentor_group_id, group.id)
        if (
            count < group.capacity
            and (chosen is None or count < chosen_count)
        ):
            chosen, chosen_count = group, count

    return chosen
