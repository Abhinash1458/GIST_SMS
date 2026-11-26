"""External trainer-only dashboard routes."""

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.deps import require_role
from app.models import Role, User
from app.services.dashboard_data import trainer_dashboard_data
from app.services.role_menus import build_role_menu


router = APIRouter(prefix="/trainer", tags=["External Trainer Dashboard"])


@router.get("")
@router.get("/")
def trainer_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    trainer: User = Depends(require_role(Role.trainer)),
):
    dashboard = trainer_dashboard_data(session, trainer)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="trainer/dashboard.html",
        context={
            "title": "External Trainer Dashboard",
            "app_name": settings.APP_NAME,
            "current_user": trainer,
            "menu_links": build_role_menu("trainer", "dashboard"),
            "dashboard": dashboard,
        },
    )
