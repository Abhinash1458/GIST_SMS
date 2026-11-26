# app/database.py

from sqlmodel import SQLModel, Session, create_engine

from app.config import settings

# Import all models to register their tables
import app.models


# SQLite connection configuration
connect_args = {}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False
    }


# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args
)


# Create all database tables
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    _add_missing_sqlite_columns()


def _add_missing_sqlite_columns():
    """Apply small, additive SQLite upgrades to existing local databases."""
    if engine.dialect.name != "sqlite":
        return

    expected_columns = {
        "student": {
            "city": "VARCHAR(100)",
        },
        "registration": {
            "city": "VARCHAR(100)",
        },
    }

    with engine.begin() as connection:
        for table_name, columns in expected_columns.items():
            table_exists = connection.exec_driver_sql(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            if not table_exists:
                continue

            existing = {
                row[1]
                for row in connection.exec_driver_sql(
                    f'PRAGMA table_info("{table_name}")'
                ).fetchall()
            }
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.exec_driver_sql(
                        f'ALTER TABLE "{table_name}" '
                        f'ADD COLUMN "{column_name}" {column_type}'
                    )


# Database session dependency
def get_session():
    with Session(engine) as session:
        yield session