
# app/deps.py

from fastapi import Request, Depends, HTTPException
from sqlmodel import Session, select
from fastapi.responses import RedirectResponse

from app.database import get_session
from app.security import decode_access_token
from app.models.users import User, Role


# ----------------------------------------
# Get Current Logged-in User
# ----------------------------------------

def get_current_user(
    request: Request,
    session: Session = Depends(get_session)
) -> User:

    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"}
        )

    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"}
        )

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"}
        )

    user = session.get(User, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"}
        )

    # Keep the authenticated user available to the friendly 403 renderer.
    request.state.current_user = user

    # Check token role against current database role
    token_role = payload.get("role")

    if token_role != user.role.value:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"}
        )

    return user


# ----------------------------------------
# Role-based Access Control
# ----------------------------------------

def require_role(*roles: Role):

    def role_checker(
        request: Request,
        current_user: User = Depends(get_current_user)
    ):

        allowed_roles = {
            role.value if isinstance(role, Role) else str(role)
            for role in roles
        }

        user_role = current_user.role.value

        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=(
                    "This area belongs to a different role. "
                    "You can only open your own dashboard."
                ),
            )

        return current_user

    return role_checker
