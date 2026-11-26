# app/routers/hod.py

"""HOD-only approval screens. Every query is scoped to the HOD's department."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.deps import get_current_user
from app.models import Department, Registration, RegistrationStatus, Role, User
from app.services import (
    AlreadyDecidedError,
    DepartmentMismatchError,
    approve_registration,
)
from app.services.dashboard_data import hod_dashboard_data
from app.services.role_menus import build_role_menu as build_role_navigation


router = APIRouter(prefix="/hod", tags=["HOD Approvals"])

DOCUMENT_FIELDS = (
    "photo_path",
    "marks_memo_path",
    "id_proof_path",
)

STATUS_LABELS = {
    "pending": "Pending",
    "approved": "Approved",
    "correction": "Sent back",
    "rejected": "Rejected",
}


def require_hod(current_user: User = Depends(get_current_user)) -> User:
    """Only users with the hod role may reach any route in this module."""
    if current_user.role != Role.hod:
        raise HTTPException(
            status_code=403,
            detail="Only HOD users can access these pages.",
        )
    return current_user


def status_value(registration: Registration) -> str:
    status = registration.status
    return status.value if hasattr(status, "value") else str(status)


def document_count(registration: Registration) -> int:
    return sum(
        1 for field in DOCUMENT_FIELDS if getattr(registration, field, None)
    )


def department_for(session: Session, hod: User) -> Department | None:
    if not hod.department_id:
        return None
    return session.get(Department, hod.department_id)


def count_registrations(
    session: Session,
    department_id: int | None,
    status: str | None = None,
    year: int | None = None,
) -> int:
    if not department_id:
        return 0

    statement = select(func.count(Registration.id)).where(
        Registration.department_id == department_id
    )

    if status:
        statement = statement.where(Registration.status == status)

    if year:
        statement = statement.where(
            Registration.submitted_at >= datetime(year, 1, 1, tzinfo=timezone.utc),
            Registration.submitted_at
            < datetime(year + 1, 1, 1, tzinfo=timezone.utc),
        )

    return session.exec(statement).one()


def scoped_registration(
    session: Session, registration_id: int, hod: User
) -> Registration | None:
    """Return a registration only when it belongs to this HOD's department."""
    if not hod.department_id:
        return None

    return session.exec(
        select(Registration).where(
            Registration.id == registration_id,
            Registration.department_id == hod.department_id,
        )
    ).first()


def build_menu(pending_count: int, active: str) -> list[dict]:
    return build_role_navigation(
        "hod",
        active,
        pending_count=pending_count,
    )


def render(
    request: Request,
    session: Session,
    hod: User,
    template_name: str,
    title: str,
    active: str = "",
    status_code: int = 200,
    **extra,
):
    pending_count = count_registrations(
        session, hod.department_id, RegistrationStatus.pending.value
    )

    context = {
        "request": request,
        "title": title,
        "app_name": settings.APP_NAME,
        "current_user": hod,
        "department": department_for(session, hod),
        "menu_links": build_menu(pending_count, active),
    }
    context.update(extra)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name=template_name,
        context=context,
        status_code=status_code,
    )


def not_found(request: Request, session: Session, hod: User):
    return render(
        request,
        session,
        hod,
        "hod/not_found.html",
        "Registration not found",
        active="registrations",
        status_code=404,
        message=(
            "That registration does not exist, or it belongs to another "
            "department."
        ),
    )


def render_detail(
    request: Request,
    session: Session,
    hod: User,
    registration: Registration,
    error: str = "",
    status_code: int = 200,
):
    return render(
        request,
        session,
        hod,
        "hod/detail.html",
        f"Registration {registration.reference_no}",
        active="registrations",
        status_code=status_code,
        registration=registration,
        status=status_value(registration),
        documents_count=document_count(registration),
        error=error,
    )


def already_decided_page(
    request: Request,
    session: Session,
    hod: User,
    registration: Registration,
    notice: str,
):
    return render(
        request,
        session,
        hod,
        "hod/result.html",
        "No action taken",
        active="registrations",
        registration=registration,
        department=department_for(session, hod),
        notice=notice,
        result=None,
    )


@router.get("")
@router.get("/")
def hod_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    department_id = hod.department_id
    pending = count_registrations(
        session, department_id, RegistrationStatus.pending.value
    )
    approved = count_registrations(
        session, department_id, RegistrationStatus.approved.value
    )
    correction = count_registrations(
        session, department_id, RegistrationStatus.correction.value
    )
    rejected = count_registrations(
        session, department_id, RegistrationStatus.rejected.value
    )
    dashboard = hod_dashboard_data(session, department_id)

    return render(
        request,
        session,
        hod,
        "hod/dashboard.html",
        "HOD Dashboard",
        active="dashboard",
        counts={
            "pending": pending,
            "approved": approved,
            "correction": correction,
            "rejected": rejected,
        },
        dashboard=dashboard,
    )


@router.get("/registrations")
def registrations(
    request: Request,
    status: str = "",
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    if status not in STATUS_LABELS and status != "":
        status = ""

    department_id = hod.department_id
    statement = select(Registration)
    if department_id:
        statement = statement.where(Registration.department_id == department_id)
    else:
        statement = statement.where(Registration.id.is_(None))

    if status:
        statement = statement.where(Registration.status == status)

    records = session.exec(
        statement.order_by(Registration.submitted_at.desc())
    ).all()

    rows = [
        {
            "registration": record,
            "status": status_value(record),
            "documents_count": document_count(record),
        }
        for record in records
    ]

    counts = {
        key: count_registrations(session, department_id, key)
        for key in STATUS_LABELS
    }
    approved_this_year = count_registrations(
        session,
        department_id,
        RegistrationStatus.approved.value,
        settings.ADMISSION_YEAR,
    )
    department = department_for(session, hod)

    return render(
        request,
        session,
        hod,
        "hod/registrations.html",
        "Registrations",
        active="registrations",
        registrations=rows,
        filter_tabs=[
            {
                "label": "All",
                "value": "",
                "count": sum(counts.values()),
            }
        ]
        + [
            {
                "label": STATUS_LABELS[key],
                "value": key,
                "count": counts[key],
            }
            for key in (
                "pending",
                "approved",
                "correction",
                "rejected",
            )
        ],
        active_filter=status,
        kpis={
            "pending": counts["pending"],
            "approved_this_year": approved_this_year,
            "intake": department.intake if department else 0,
            "correction": counts["correction"],
            "rejected": counts["rejected"],
        },
    )


@router.get("/registrations/{registration_id}")
def registration_detail(
    request: Request,
    registration_id: int,
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    registration = scoped_registration(session, registration_id, hod)
    if not registration:
        return not_found(request, session, hod)

    return render_detail(request, session, hod, registration)


@router.post("/registrations/{registration_id}/approve")
def approve(
    request: Request,
    registration_id: int,
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    registration = scoped_registration(session, registration_id, hod)
    if not registration:
        return not_found(request, session, hod)

    if status_value(registration) != RegistrationStatus.pending.value:
        return already_decided_page(
            request,
            session,
            hod,
            registration,
            "This registration is no longer pending "
            f"(status: {STATUS_LABELS.get(status_value(registration), status_value(registration))}). "
            "No action was taken.",
        )

    try:
        result = approve_registration(session, registration, hod)
    except AlreadyDecidedError as exc:
        return already_decided_page(
            request, session, hod, registration, exc.message
        )
    except DepartmentMismatchError as exc:
        raise HTTPException(status_code=403, detail=exc.message)

    return render(
        request,
        session,
        hod,
        "hod/result.html",
        "Approval complete",
        active="registrations",
        result=result,
        registration=registration,
        department=department_for(session, hod),
        notice="",
    )


@router.post("/registrations/{registration_id}/reject")
def reject(
    request: Request,
    registration_id: int,
    remarks: str = Form(""),
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    return _decide_with_remarks(
        request,
        session,
        hod,
        registration_id,
        remarks,
        RegistrationStatus.rejected,
    )


@router.post("/registrations/{registration_id}/correction")
def correction(
    request: Request,
    registration_id: int,
    remarks: str = Form(""),
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    return _decide_with_remarks(
        request,
        session,
        hod,
        registration_id,
        remarks,
        RegistrationStatus.correction,
    )


def _decide_with_remarks(
    request: Request,
    session: Session,
    hod: User,
    registration_id: int,
    remarks: str,
    new_status: RegistrationStatus,
):
    registration = scoped_registration(session, registration_id, hod)
    if not registration:
        return not_found(request, session, hod)

    if status_value(registration) != RegistrationStatus.pending.value:
        return already_decided_page(
            request,
            session,
            hod,
            registration,
            "This registration is no longer pending. No action was taken.",
        )

    remarks = remarks.strip()
    if not remarks:
        return render_detail(
            request,
            session,
            hod,
            registration,
            error="Remarks are required before you can "
            f"{'reject' if new_status == RegistrationStatus.rejected else 'send back'} "
            "an application.",
            status_code=400,
        )

    registration.status = new_status
    registration.hod_remarks = remarks
    registration.decided_at = datetime.now(timezone.utc)
    registration.decided_by_user_id = hod.id
    session.add(registration)
    session.commit()

    return RedirectResponse(
        url=f"/hod/registrations/{registration_id}",
        status_code=303,
    )


def render_placeholder(
    request: Request,
    session: Session,
    hod: User,
    title: str,
    active: str,
):
    return render(
        request,
        session,
        hod,
        "hod/placeholder.html",
        title,
        active=active,
    )


@router.get("/students")
def students_page(
    request: Request,
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    return render_placeholder(request, session, hod, "Students", "students")


@router.get("/mentor-groups")
def mentor_groups_page(
    request: Request,
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    return render_placeholder(
        request, session, hod, "Mentor groups", "mentor-groups"
    )


@router.get("/subjects")
def subjects_page(
    request: Request,
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    return render_placeholder(request, session, hod, "Subjects", "subjects")


@router.get("/leave-requests")
def leave_requests_page(
    request: Request,
    session: Session = Depends(get_session),
    hod: User = Depends(require_hod),
):
    return render_placeholder(
        request, session, hod, "Leave requests", "leave-requests"
    )
