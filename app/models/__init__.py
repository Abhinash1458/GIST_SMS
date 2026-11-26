
# app/models/__init__.py

from app.models.users import User, Role

from app.models.aca import (
    StudentStatus,
    Department,
    Batch,
    Section,
    MentorGroup,
    Student,
    Subject,
    TeachingAssignment,
    RollCounter,
)

from app.models.registration import (
    RegistrationStatus,
    Registration,
)

from app.models.later import (
    AttendanceStatus,
    ExamType,
    LeaveStatus,
    Attendance,
    Mark,
    Exam,
    ExamSchedule,
    HallTicket,
    LeaveRequest,
    Notice,
)

__all__ = [
    "User",
    "Role",
    "StudentStatus",
    "Department",
    "Batch",
    "Section",
    "MentorGroup",
    "Student",
    "Subject",
    "TeachingAssignment",
    "RollCounter",
    "RegistrationStatus",
    "Registration",
    "AttendanceStatus",
    "ExamType",
    "LeaveStatus",
    "Attendance",
    "Mark",
    "Exam",
    "ExamSchedule",
    "HallTicket",
    "LeaveRequest",
    "Notice",
]
