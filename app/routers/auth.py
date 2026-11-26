
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.database import get_session
from app.models.users import User
from app.security import verify_password, create_access_token
from app.config import settings
from app.deps import get_current_user

router = APIRouter(tags=["Authentication"])

ROLE_DASHBOARDS = {
    "management": "/management",
    "hod": "/hod",
    "mentor": "/mentor",
    "trainer": "/trainer",
    "student": "/student",
}


@router.get("/login")
def login_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "title": "Login",
            "app_name": settings.APP_NAME,
            "error": None
        }
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    user = session.exec(
        select(User).where(User.username == username.strip())
    ).first()

    if not user or not verify_password(password, user.password_hash):
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "title": "Login",
                "app_name": settings.APP_NAME,
                "error": "Wrong username or password"
            },
            status_code=401
        )

    if not user.is_active:
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "title": "Login",
                "app_name": settings.APP_NAME,
                "error": "Your account is inactive. Contact management."
            },
            status_code=403
        )

    token = create_access_token(user.id, user.role.value)

    if user.must_change_password:
        redirect_url = "/change-password"
    else:
        redirect_url = ROLE_DASHBOARDS[user.role.value]

    response = RedirectResponse(
        url=redirect_url,
        status_code=303
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_MINUTES * 60,
        path="/",
        secure=False
    )

    return response


@router.get("/change-password")
def change_password_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="change_password.html",
        context={
            "title": "Change Password",
            "user": current_user,
            "error": None
        }
    )


@router.post("/change-password")
def change_password(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    from app.security import hash_password

    error = None

    if len(new_password) < 8:
        error = "Password must contain at least 8 characters."
    elif len(new_password.encode("utf-8")) > 72:
        error = "Password is too long."
    elif new_password != confirm_password:
        error = "Passwords do not match."

    if error:
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="change_password.html",
            context={
                "title": "Change Password",
                "user": current_user,
                "error": error
            },
            status_code=400
        )

    current_user.password_hash = hash_password(new_password)
    current_user.must_change_password = False

    session.add(current_user)
    session.commit()

    return RedirectResponse(
        url=ROLE_DASHBOARDS[current_user.role.value],
        status_code=303
    )


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        samesite="lax"
    )
    return response
