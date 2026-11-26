"""Management dashboard and the only place that links to SQLADMIN."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.deps import get_current_user
from app.models import Role, User
from app.services.dashboard_data import management_dashboard_data
from app.services.role_menus import build_role_menu


router = APIRouter(tags=["Management"])


def require_management(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != Role.management:
        raise HTTPException(
            status_code=403,
            detail=(
                "The management dashboard is available only to Management "
                "users."
            ),
        )
    return current_user


@router.get("/management")
def dashboard(
    request: Request,
    session: Session = Depends(get_session),
    management: User = Depends(require_management),
):
    dashboard_data = management_dashboard_data(session)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="management/dashboard.html",
        context={
            "title": "Management Dashboard",
            "app_name": settings.APP_NAME,
            "current_user": management,
            "menu_links": build_role_menu(
                "management",
                "dashboard",
                pending_count=dashboard_data["pending_registrations"],
            ),
            "dashboard": dashboard_data,
        },
    )
