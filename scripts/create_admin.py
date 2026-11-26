
# scripts/create_admin.py

import sys
from pathlib import Path

# Add project root to Python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlmodel import Session, select

from app.database import engine, create_db_and_tables
from app.models.users import User, Role
from app.security import hash_password


USERNAME = "management@college.edu"
PASSWORD = "Admin@123"


def create_admin():

    # Ensure all registered tables exist
    create_db_and_tables()

    with Session(engine) as session:

        # Check whether admin already exists
        statement = select(User).where(
            User.username == USERNAME
        )

        existing_user = session.exec(statement).first()

        if existing_user:

            print("Management account already exists.")
            return

        # Create management account
        admin = User(
            username=USERNAME,
            full_name="GIST Management",
            email=USERNAME,
            password_hash=hash_password(PASSWORD),
            role=Role.management,
            department_id=None,
            is_active=True,
            must_change_password=False
        )

        session.add(admin)
        session.commit()
        session.refresh(admin)

        print("----------------------------------")
        print("Management account created!")
        print("----------------------------------")
        print("Username:", USERNAME)
        print("Password:", PASSWORD)
        print("Role:", admin.role.value)
        print("User ID:", admin.id)
        print("----------------------------------")


if __name__ == "__main__":
    create_admin()
