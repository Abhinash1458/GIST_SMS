# app/services/roll_number.py

"""Plain roll-number allocation. No web framework code lives here."""

from sqlmodel import Session, select

from app.models import Department, RollCounter


def next_roll_number(
    session: Session, department: Department, admission_year: int
) -> str:
    """
    Allocate the next serial for a department and admission year.

    A counter table is safer than counting Student rows: students can be
    deleted, transferred or re-created, and a failed approval can leave a gap,
    so counting can hand the same number to two people. RollCounter is a
    monotonic, unique (department_id, admission_year) sequence whose increment
    is part of the same transaction as the student creation.
    """
    counter = session.exec(
        select(RollCounter).where(
            RollCounter.department_id == department.id,
            RollCounter.admission_year == admission_year,
        )
    ).first()

    if not counter:
        counter = RollCounter(
            department_id=department.id,
            admission_year=admission_year,
            last_serial=0,
        )
        session.add(counter)
        session.flush()

    counter.last_serial += 1
    session.add(counter)
    session.flush()

    return (
        f"{admission_year % 100:02d}{department.code}{counter.last_serial:03d}"
    )
