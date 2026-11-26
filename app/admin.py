# app/admin.py

"""
SQLADMIN setup for GIST SMS.

This module wires sqladmin into the FastAPI app at /admin. It deliberately
keeps a separate, signed session cookie for the admin area and refuses every
account except Role.management. User.password_hash is excluded from list,
detail, create/edit and export views so it can never be displayed or edited
from the admin screens.
"""

from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlmodel import Session, select
from starlette.requests import Request
from starlette.responses import Response

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
    Role,
    RollCounter,
    Section,
    Student,
    Subject,
    TeachingAssignment,
    User,
)
from app.security import verify_password


# ----------------------------------------------------------------------
# Authentication: dedicated /admin session, signed with the app secret
# ----------------------------------------------------------------------


class ManagementAuthBackend(AuthenticationBackend):
    """Authenticate SQLADMIN users against the application's User table."""

    def __init__(self, templates):
        # SessionMiddleware is installed by sqladmin only on its sub-app.
        super().__init__(
            secret_key=settings.SECRET_KEY,
            session_cookie="admin_session",
            max_age=settings.ACCESS_TOKEN_MINUTES * 60,
            same_site="lax",
            https_only=False,
            path="/admin",
        )
        self.templates = templates

    async def _deny(self, request: Request, message: str, status_code: int):
        """Re-render the admin login page with a specific reason."""
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/login.html",
            {"error": message},
            status_code=status_code,
        )

    async def login(self, request: Request) -> Response | bool:
        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))

        with Session(engine) as session:
            user = session.exec(
                select(User).where(User.username == username)
            ).first()

            if not user or not verify_password(password, user.password_hash):
                return await self._deny(
                    request, "Wrong username or password.", 401
                )

            if not user.is_active:
                return await self._deny(
                    request, "This account is inactive.", 403
                )

            if user.role != Role.management:
                return await self._deny(
                    request,
                    "Only Management accounts can access SQLADMIN.",
                    403,
                )

            # Re-check the role on every request, not just at login.
            request.session["user_id"] = user.id
            request.session["username"] = user.username
            request.session["role"] = user.role.value

        return True

    async def authenticate(self, request: Request) -> Response | bool:
        user_id = request.session.get("user_id")

        if not user_id:
            return False

        with Session(engine) as session:
            user = session.get(User, user_id)

            if (
                not user
                or not user.is_active
                or user.role != Role.management
            ):
                request.session.clear()
                return False

        return True

    async def logout(self, request: Request) -> Response | bool:
        request.session.clear()
        return True


# ----------------------------------------------------------------------
# Model views
# ----------------------------------------------------------------------


class BaseAdminView(ModelView):
    """Shared defaults: no bulk delete and no CSV export of secrets."""

    can_export = False
    can_delete = False
    column_default_sort = ("id", True)
    page_size = 25


class UserAdmin(BaseAdminView, model=User):
    category = "People"
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-users"

    column_list = [
        "id",
        "username",
        "full_name",
        "email",
        "role",
        "department_id",
        "is_active",
        "must_change_password",
        "created_at",
    ]
    column_searchable_list = ["username", "role"]
    # The hash is never listed, detailed, edited, imported or exported.
    column_details_exclude_list = ["password_hash"]
    column_export_exclude_list = ["password_hash"]
    column_import_exclude_list = ["password_hash"]
    form_columns = [
        "username",
        "full_name",
        "email",
        "role",
        "department_id",
        "is_active",
        "must_change_password",
    ]


class StudentAdmin(BaseAdminView, model=Student):
    category = "People"
    name = "Student"
    name_plural = "Students"
    icon = "fa-solid fa-user-graduate"

    column_list = [
        "id",
        "roll_number",
        "full_name",
        "department_id",
        "section_id",
        "city",
        "mentor_group_id",
        "admission_year",
        "status",
    ]
    column_searchable_list = ["roll_number", "full_name"]
    form_columns = [
        "user_id",
        "roll_number",
        "full_name",
        "dob",
        "gender",
        "phone",
        "city",
        "email",
        "parent_name",
        "department_id",
        "batch_id",
        "section_id",
        "mentor_group_id",
        "quota",
        "admission_year",
        "status",
    ]


class DepartmentAdmin(BaseAdminView, model=Department):
    category = "Academics"
    name = "Department"
    name_plural = "Departments"
    icon = "fa-solid fa-building-columns"

    column_list = ["id", "code", "name", "intake", "hod_user_id"]
    column_searchable_list = ["code", "name"]


class BatchAdmin(BaseAdminView, model=Batch):
    category = "Academics"
    name = "Batch"
    name_plural = "Batches"
    icon = "fa-solid fa-layer-group"

    column_list = ["id", "department_id", "start_year", "end_year"]
    column_searchable_list = ["start_year"]


class SectionAdmin(BaseAdminView, model=Section):
    category = "Academics"
    name = "Section"
    name_plural = "Sections"
    icon = "fa-solid fa-chalkboard"

    column_list = [
        "id",
        "batch_id",
        "name",
        "current_year",
        "current_semester",
        "capacity",
    ]
    column_searchable_list = ["name"]


class MentorGroupAdmin(BaseAdminView, model=MentorGroup):
    category = "Academics"
    name = "Mentor group"
    name_plural = "Mentor groups"
    icon = "fa-solid fa-people-group"

    column_list = ["id", "section_id", "name", "mentor_user_id", "capacity"]
    column_searchable_list = ["name"]


class SubjectAdmin(BaseAdminView, model=Subject):
    category = "Academics"
    name = "Subject"
    name_plural = "Subjects"
    icon = "fa-solid fa-book"

    column_list = [
        "id",
        "code",
        "name",
        "department_id",
        "year",
        "semester",
        "credits",
    ]
    column_searchable_list = ["code", "name"]


class TeachingAssignmentAdmin(BaseAdminView, model=TeachingAssignment):
    category = "Academics"
    name = "Teaching assignment"
    name_plural = "Teaching assignments"
    icon = "fa-solid fa-chalkboard-user"

    column_list = ["id", "subject_id", "section_id", "teacher_user_id"]


class RollCounterAdmin(BaseAdminView, model=RollCounter):
    category = "Academics"
    name = "Roll counter"
    name_plural = "Roll counters"
    icon = "fa-solid fa-hashtag"

    column_list = ["id", "department_id", "admission_year", "last_serial"]
    column_searchable_list = ["admission_year"]


class RegistrationAdmin(BaseAdminView, model=Registration):
    category = "Admissions"
    name = "Registration"
    name_plural = "Registrations"
    icon = "fa-solid fa-file-circle-check"

    column_list = [
        "id",
        "reference_no",
        "full_name",
        "department_id",
        "quota",
        "entrance_rank",
        "inter_percent",
        "status",
        "submitted_at",
    ]
    column_searchable_list = ["reference_no", "status"]


class AttendanceAdmin(BaseAdminView, model=Attendance):
    category = "Exams and attendance"
    name = "Attendance"
    name_plural = "Attendance"
    icon = "fa-solid fa-calendar-check"

    column_list = [
        "id",
        "student_id",
        "section_id",
        "date",
        "period",
        "status",
        "marked_by_user_id",
    ]
    column_searchable_list = ["date", "status"]


class MarkAdmin(BaseAdminView, model=Mark):
    category = "Exams and attendance"
    name = "Mark"
    name_plural = "Marks"
    icon = "fa-solid fa-graduation-cap"

    column_list = [
        "id",
        "student_id",
        "subject_id",
        "exam_type",
        "max_marks",
        "marks_obtained",
        "entered_by_user_id",
    ]
    column_searchable_list = ["exam_type"]


class ExamAdmin(BaseAdminView, model=Exam):
    category = "Exams and attendance"
    name = "Exam"
    name_plural = "Exams"
    icon = "fa-solid fa-file-pen"

    column_list = [
        "id",
        "name",
        "department_id",
        "year",
        "semester",
        "start_date",
        "end_date",
        "is_published",
    ]
    column_searchable_list = ["name"]


class ExamScheduleAdmin(BaseAdminView, model=ExamSchedule):
    category = "Exams and attendance"
    name = "Exam schedule"
    name_plural = "Exam schedules"
    icon = "fa-solid fa-calendar-days"

    column_list = ["id", "exam_id", "subject_id", "exam_date", "session", "room"]
    column_searchable_list = ["room"]


class HallTicketAdmin(BaseAdminView, model=HallTicket):
    category = "Exams and attendance"
    name = "Hall ticket"
    name_plural = "Hall tickets"
    icon = "fa-solid fa-ticket"

    column_list = [
        "id",
        "ticket_no",
        "exam_id",
        "student_id",
        "is_eligible",
        "generated_at",
    ]
    column_searchable_list = ["ticket_no"]


class LeaveRequestAdmin(BaseAdminView, model=LeaveRequest):
    category = "Exams and attendance"
    name = "Leave request"
    name_plural = "Leave requests"
    icon = "fa-solid fa-calendar-minus"

    column_list = [
        "id",
        "student_id",
        "from_date",
        "to_date",
        "status",
        "decided_by_user_id",
    ]
    column_searchable_list = ["status"]


class NoticeAdmin(BaseAdminView, model=Notice):
    category = "Exams and attendance"
    name = "Notice"
    name_plural = "Notices"
    icon = "fa-solid fa-bullhorn"

    column_list = [
        "id",
        "title",
        "audience",
        "department_id",
        "section_id",
        "role",
        "created_at",
    ]
    column_searchable_list = ["title", "audience"]


ADMIN_VIEWS = (
    UserAdmin,
    StudentAdmin,
    DepartmentAdmin,
    BatchAdmin,
    SectionAdmin,
    MentorGroupAdmin,
    SubjectAdmin,
    TeachingAssignmentAdmin,
    RollCounterAdmin,
    RegistrationAdmin,
    AttendanceAdmin,
    MarkAdmin,
    ExamAdmin,
    ExamScheduleAdmin,
    HallTicketAdmin,
    LeaveRequestAdmin,
    NoticeAdmin,
)


def setup_admin(app: FastAPI, templates, templates_dir: str) -> Admin:
    """Mount the SQLADMIN interface at /admin."""
    admin = Admin(
        app=app,
        engine=engine,
        base_url="/admin",
        title="GIST SMS SQLADMIN",
        templates_dir=templates_dir,
        authentication_backend=ManagementAuthBackend(templates),
    )

    # Render login errors with sqladmin's own Jinja environment, which knows
    # the admin globals and URL routes used by its base template.
    admin.authentication_backend.templates = admin.templates

    for view in ADMIN_VIEWS:
        admin.add_view(view)

    return admin
