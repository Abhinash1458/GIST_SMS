# scripts/create_hod_users.py

import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.models import Department, Role, User
from app.security import hash_password


PASSWORD = "Hod@12345"


def username_for(department: Department) -> str:
    code = department.code.lower().replace("&", "")
    return f"hod.{code}@college.edu"


def create_hod_users():
    create_db_and_tables()

    created = []
    existing = []

    with Session(engine) as session:
        departments = session.exec(
            select(Department).order_by(Department.id)
        ).all()

        for department in departments:
            username = username_for(department)

            user = session.exec(
                select(User).where(User.username == username)
            ).first()

            if not user:
                user = session.exec(
                    select(User).where(
                        User.role == Role.hod,
                        User.department_id == department.id,
                    )
                ).first()

            if user:
                existing.append((department.code, user.username))
                if not department.hod_user_id:
                    department.hod_user_id = user.id
                    session.add(department)
                continue

            user = User(
                username=username,
                full_name=f"{department.code} HOD",
                email=username,
                password_hash=hash_password(PASSWORD),
                role=Role.hod,
                department_id=department.id,
                is_active=True,
                must_change_password=False,
                created_at=datetime.now(timezone.utc),
            )
            session.add(user)
            session.flush()

            department.hod_user_id = user.id
            session.add(department)
            created.append((department.code, username))

        session.commit()

    print("----------------------------------")
    print(f"HOD accounts created: {len(created)}")
    for code, username in created:
        print(f"  {code:<8} {username}  /  {PASSWORD}")
    if existing:
        print(f"Already present: {len(existing)}")
        for code, username in existing:
            print(f"  {code:<8} {username}")
    print("----------------------------------")


if __name__ == "__main__":
    create_hod_users()
