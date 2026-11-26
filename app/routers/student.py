"""Student-only dashboard routes."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.deps import require_role
from app.models import Role, User
from app.services.dashboard_data import student_dashboard_data
from app.services.role_menus import build_role_menu


router = APIRouter(prefix="/student", tags=["Student Dashboard"])


@router.get("")
@router.get("/")
def student_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    student_user: User = Depends(require_role(Role.student)),
):
    dashboard = student_dashboard_data(session, student_user)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="student/dashboard.html",
        context={
            "title": "Student Dashboard",
            "app_name": settings.APP_NAME,
            "current_user": student_user,
            "menu_links": build_role_menu("student", "dashboard"),
            **dashboard,
        },
    )
