"""Mentor-only dashboard routes."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.deps import require_role
from app.models import Role, User
from app.services.dashboard_data import mentor_dashboard_data
from app.services.role_menus import build_role_menu


router = APIRouter(prefix="/mentor", tags=["Mentor Dashboard"])


@router.get("")
@router.get("/")
def mentor_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    mentor: User = Depends(require_role(Role.mentor)),
):
    dashboard = mentor_dashboard_data(session, mentor)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="mentor/dashboard.html",
        context={
            "title": "Mentor Dashboard",
            "app_name": settings.APP_NAME,
            "current_user": mentor,
            "menu_links": build_role_menu("mentor", "dashboard"),
            **dashboard,
        },
    )
