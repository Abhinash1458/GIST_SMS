
# app/routers/register.py

from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select
from sqlalchemy import func

from app.config import settings
from app.database import get_session
from app.models import (
    Department,
    Registration,
    RegistrationStatus,
    Student,
)


router = APIRouter(tags=["Public Registration"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_ROOT = BASE_DIR / "app" / "static" / "uploads" / "registrations"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_FILE_SIZE = 2 * 1024 * 1024

STEP_PERSONAL = 0
STEP_ACADEMIC = 1
STEP_DOCUMENTS = 2
STEP_REVIEW = 3


class FormError(ValueError):
    """Validation error that knows which form step to reopen."""

    def __init__(self, message: str, step: int = STEP_PERSONAL):
        super().__init__(message)
        self.step = step


def get_templates(request: Request):
    return request.app.state.templates


def get_departments(session: Session):
    statement = select(Department).order_by(Department.name)
    return session.exec(statement).all()


def render_form(
    request: Request,
    session: Session,
    error: str = "",
    values: dict | None = None,
    template: str = "register/form.html",
    registration: Registration | None = None,
    step: int = STEP_PERSONAL,
    status_code: int = 200,
):
    today = date.today()
    try:
        latest_dob = today.replace(year=today.year - 16)
    except ValueError:
        latest_dob = today.replace(
            year=today.year - 16, month=2, day=28
        )

    return get_templates(request).TemplateResponse(
        request=request,
        name=template,
        context={
            "request": request,
            "title": (
                "Edit registration" if registration
                else "Student Registration"
            ),
            "departments": get_departments(session),
            "error": error,
            "values": values or {},
            "registration": registration,
            "step": step,
            "latest_dob": latest_dob.isoformat(),
        },
        status_code=status_code,
    )


def calculate_age(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )


def validate_details(
    full_name: str,
    dob_value: str,
    gender: str,
    phone: str,
    email: str,
    parent_name: str,
    department_id: str,
    quota: str,
    tenth_percent: str,
    inter_percent: str,
    entrance_rank: str,
    session: Session,
):
    full_name = full_name.strip()
    phone = phone.strip()
    email = email.strip().lower()
    parent_name = parent_name.strip()
    quota = quota.strip()
    gender = gender.strip()

    if not all([
        full_name, dob_value, gender, phone,
        email, parent_name, quota,
        tenth_percent, inter_percent,
    ]):
        raise FormError(
            "Please fill in all required fields.", STEP_PERSONAL
        )

    if len(phone) != 10 or not phone.isdigit():
        raise FormError(
            "Phone number must contain exactly 10 digits.", STEP_PERSONAL
        )

    if "@" not in email or "." not in email.split("@")[-1]:
        raise FormError(
            "Please enter a valid email address.", STEP_PERSONAL
        )

    try:
        dob = date.fromisoformat(dob_value)
    except ValueError:
        raise FormError(
            "Please enter a valid date of birth.", STEP_PERSONAL
        )

    if dob >= date.today():
        raise FormError(
            "Date of birth must be in the past.", STEP_PERSONAL
        )

    if calculate_age(dob) < 16:
        raise FormError(
            "The applicant must be at least 16 years old.", STEP_PERSONAL
        )

    try:
        tenth = float(tenth_percent)
        inter = float(inter_percent)
    except ValueError:
        raise FormError(
            "Please enter valid percentage values.", STEP_ACADEMIC
        )

    if not 0 <= tenth <= 100:
        raise FormError(
            "10th percentage must be between 0 and 100.", STEP_ACADEMIC
        )

    if not 0 <= inter <= 100:
        raise FormError(
            "Intermediate percentage must be between 0 and 100.",
            STEP_ACADEMIC,
        )

    try:
        department_id_int = int(department_id)
    except (TypeError, ValueError):
        raise FormError(
            "Please select a valid department.", STEP_ACADEMIC
        )

    department = session.get(Department, department_id_int)
    if not department:
        raise FormError(
            "Please select a valid department.", STEP_ACADEMIC
        )

    rank = None
    if entrance_rank.strip():
        try:
            rank = int(entrance_rank)
            if rank <= 0:
                raise ValueError
        except ValueError:
            raise FormError(
                "Entrance rank must be a positive whole number.",
                STEP_ACADEMIC,
            )

    return {
        "full_name": full_name,
        "dob": dob,
        "gender": gender,
        "phone": phone,
        "email": email,
        "parent_name": parent_name,
        "department_id": department_id_int,
        "quota": quota,
        "entrance_rank": rank,
        "tenth_percent": tenth,
        "inter_percent": inter,
    }


async def read_upload(
    upload: UploadFile | None,
    required: bool,
    label: str,
):
    if upload is None or not upload.filename:
        if required:
            raise FormError(f"{label} is required.", STEP_DOCUMENTS)
        return None

    extension = Path(upload.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise FormError(
            f"{label}: only JPG, JPEG, PNG and PDF files are allowed.",
            STEP_DOCUMENTS,
        )

    content = await upload.read(MAX_FILE_SIZE + 1)

    if not content:
        raise FormError(
            f"{label} cannot be an empty file.", STEP_DOCUMENTS
        )

    if len(content) > MAX_FILE_SIZE:
        raise FormError(
            f"{label} must not exceed 2 MB. "
            f"Your file is {len(content) / (1024 * 1024):.1f} MB.",
            STEP_DOCUMENTS,
        )

    return {
        "extension": extension,
        "content": content,
    }


def save_uploads(reference_no: str, files: dict):
    folder = UPLOAD_ROOT / reference_no
    folder.mkdir(parents=True, exist_ok=True)

    saved_paths = {}
    written = []

    try:
        for field_name, file_data in files.items():
            if file_data is None:
                continue

            extension = file_data["extension"]
            filename = f"{field_name}{extension}"
            destination = folder / filename

            destination.write_bytes(file_data["content"])
            written.append(destination)

            saved_paths[field_name] = (
                f"uploads/registrations/{reference_no}/{filename}"
            )

            # Remove a previous version saved with another extension.
            for existing in folder.glob(f"{field_name}.*"):
                if existing != destination:
                    existing.unlink(missing_ok=True)

        return saved_paths

    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise


def next_reference_number(session: Session) -> str:
    highest_id = session.exec(
        select(func.max(Registration.id))
    ).one()

    next_id = (highest_id or 0) + 1
    return f"REG-{settings.ADMISSION_YEAR}-{next_id:05d}"


def registration_status_value(registration: Registration) -> str:
    value = registration.status
    return value.value if hasattr(value, "value") else str(value)


def render_status(
    request: Request,
    session: Session,
    registration: Registration,
):
    department = session.get(Department, registration.department_id)
    student = (
        session.get(Student, registration.student_id)
        if registration.student_id else None
    )

    return get_templates(request).TemplateResponse(
        request=request,
        name="register/status_result.html",
        context={
            "request": request,
            "title": "Application status",
            "registration": registration,
            "department": department,
            "student": student,
            "status_value": registration_status_value(registration),
        },
    )


@router.get("/register")
def registration_form(
    request: Request,
    session: Session = Depends(get_session),
):
    return render_form(request, session)


@router.post("/register")
async def submit_registration(
    request: Request,
    full_name: str = Form(...),
    dob: str = Form(...),
    gender: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    parent_name: str = Form(...),
    department_id: str = Form(...),
    quota: str = Form(...),
    tenth_percent: str = Form(...),
    inter_percent: str = Form(...),
    entrance_rank: str = Form(""),
    photo: UploadFile | None = File(None),
    marks_memo: UploadFile | None = File(None),
    id_proof: UploadFile | None = File(None),
    session: Session = Depends(get_session),
):
    values = {
        "full_name": full_name,
        "dob": dob,
        "gender": gender,
        "phone": phone,
        "email": email,
        "parent_name": parent_name,
        "department_id": department_id,
        "quota": quota,
        "tenth_percent": tenth_percent,
        "inter_percent": inter_percent,
        "entrance_rank": entrance_rank,
    }

    try:
        details = validate_details(
            full_name, dob, gender, phone, email,
            parent_name, department_id, quota,
            tenth_percent, inter_percent, entrance_rank, session,
        )

        files = {
            "photo": await read_upload(photo, True, "Photo"),
            "marks_memo": await read_upload(
                marks_memo, True, "Marks memo"
            ),
            "id_proof": await read_upload(
                id_proof, True, "ID proof"
            ),
        }

        reference_no = next_reference_number(session)
        saved_paths = save_uploads(reference_no, files)

        registration = Registration(
            **details,
            reference_no=reference_no,
            photo_path=saved_paths["photo"],
            marks_memo_path=saved_paths["marks_memo"],
            id_proof_path=saved_paths["id_proof"],
            status=RegistrationStatus.pending,
            submitted_at=datetime.now(timezone.utc),
        )

        session.add(registration)
        session.commit()

        return RedirectResponse(
            url=f"/register/done/{reference_no}",
            status_code=303,
        )

    except FormError as exc:
        return render_form(
            request,
            session,
            error=str(exc),
            values=values,
            step=exc.step,
            status_code=400,
        )

    except Exception:
        session.rollback()
        raise


@router.get("/register/done/{reference_no}")
def registration_success(
    request: Request,
    reference_no: str,
    session: Session = Depends(get_session),
):
    registration = session.exec(
        select(Registration).where(
            Registration.reference_no == reference_no
        )
    ).first()

    if not registration:
        return get_templates(request).TemplateResponse(
            request=request,
            name="register/not_found.html",
            context={
                "request": request,
                "title": "Application not found",
            },
            status_code=404,
        )

    return get_templates(request).TemplateResponse(
        request=request,
        name="register/done.html",
        context={
            "request": request,
            "title": "Registration complete",
            "registration": registration,
        },
    )


@router.get("/register/status")
def registration_status_form(
    request: Request,
    reference_no: str = "",
    session: Session = Depends(get_session),
):
    reference_no = reference_no.strip().upper()

    if reference_no:
        registration = session.exec(
            select(Registration).where(
                Registration.reference_no == reference_no
            )
        ).first()

        if registration:
            return render_status(request, session, registration)

    return get_templates(request).TemplateResponse(
        request=request,
        name="register/status_form.html",
        context={
            "request": request,
            "title": "Track application",
            "reference_no": reference_no,
            "error": "",
        },
    )


@router.post("/register/status")
def check_registration_status(
    request: Request,
    reference_no: str = Form(...),
    session: Session = Depends(get_session),
):
    reference_no = reference_no.strip().upper()

    registration = session.exec(
        select(Registration).where(
            Registration.reference_no == reference_no
        )
    ).first()

    if not registration:
        return get_templates(request).TemplateResponse(
            request=request,
            name="register/status_form.html",
            context={
                "request": request,
                "title": "Track application",
                "reference_no": reference_no,
                "error": "No application found with that reference number.",
            },
            status_code=404,
        )

    return render_status(request, session, registration)


@router.get("/register/status/edit/{reference_no}")
def edit_registration_form(
    request: Request,
    reference_no: str,
    session: Session = Depends(get_session),
):
    registration = session.exec(
        select(Registration).where(
            Registration.reference_no == reference_no
        )
    ).first()

    if (
        not registration
        or registration_status_value(registration) != "correction"
    ):
        return RedirectResponse("/register/status", status_code=303)

    values = {
        "full_name": registration.full_name,
        "dob": registration.dob.isoformat(),
        "gender": registration.gender,
        "phone": registration.phone,
        "email": registration.email,
        "parent_name": registration.parent_name,
        "department_id": registration.department_id,
        "quota": registration.quota,
        "tenth_percent": registration.tenth_percent,
        "inter_percent": registration.inter_percent,
        "entrance_rank": registration.entrance_rank or "",
    }

    return render_form(
        request,
        session,
        values=values,
        template="register/edit.html",
        registration=registration,
    )


@router.post("/register/status/edit/{reference_no}")
async def resubmit_registration(
    request: Request,
    reference_no: str,
    full_name: str = Form(...),
    dob: str = Form(...),
    gender: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    parent_name: str = Form(...),
    department_id: str = Form(...),
    quota: str = Form(...),
    tenth_percent: str = Form(...),
    inter_percent: str = Form(...),
    entrance_rank: str = Form(""),
    photo: UploadFile | None = File(None),
    marks_memo: UploadFile | None = File(None),
    id_proof: UploadFile | None = File(None),
    session: Session = Depends(get_session),
):
    registration = session.exec(
        select(Registration).where(
            Registration.reference_no == reference_no
        )
    ).first()

    if (
        not registration
        or registration_status_value(registration) != "correction"
    ):
        return RedirectResponse("/register/status", status_code=303)

    values = {
        "full_name": full_name,
        "dob": dob,
        "gender": gender,
        "phone": phone,
        "email": email,
        "parent_name": parent_name,
        "department_id": department_id,
        "quota": quota,
        "tenth_percent": tenth_percent,
        "inter_percent": inter_percent,
        "entrance_rank": entrance_rank,
    }

    try:
        details = validate_details(
            full_name, dob, gender, phone, email,
            parent_name, department_id, quota,
            tenth_percent, inter_percent, entrance_rank, session,
        )

        files = {
            "photo": await read_upload(photo, False, "Photo"),
            "marks_memo": await read_upload(
                marks_memo, False, "Marks memo"
            ),
            "id_proof": await read_upload(
                id_proof, False, "ID proof"
            ),
        }

        saved_paths = (
            save_uploads(reference_no, files)
            if any(files.values()) else {}
        )

        for field, value in details.items():
            setattr(registration, field, value)

        for field, path in saved_paths.items():
            setattr(registration, f"{field}_path", path)

        registration.status = RegistrationStatus.pending
        registration.hod_remarks = None
        registration.decided_at = None
        registration.decided_by_user_id = None
        registration.submitted_at = datetime.now(timezone.utc)

        session.add(registration)
        session.commit()

        return RedirectResponse(
            url=f"/register/status?reference_no={reference_no}",
            status_code=303,
        )

    except FormError as exc:
        return render_form(
            request,
            session,
            error=str(exc),
            values=values,
            template="register/edit.html",
            registration=registration,
            step=exc.step,
            status_code=400,
        )

    except Exception:
        session.rollback()
        raise
