
# app/security.py

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


ALGORITHM = "HS256"


# ----------------------------------------
# Password Hashing
# ----------------------------------------

def hash_password(password: str) -> str:
    """
    Convert plain password into a secure bcrypt hash.
    """

    password_bytes = password.encode("utf-8")

    hashed = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt()
    )

    return hashed.decode("utf-8")


# ----------------------------------------
# Password Verification
# ----------------------------------------

def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    """
    Check whether the entered password matches the stored hash.
    """

    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )

    except (ValueError, TypeError):
        return False


# ----------------------------------------
# JWT Token Creation
# ----------------------------------------

def create_access_token(
    user_id: int,
    role: str
) -> str:
    """
    Generate JWT token with user ID, role and expiry.
    """

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire
    }

    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token


# ----------------------------------------
# JWT Token Verification
# ----------------------------------------

def decode_access_token(token: str) -> dict | None:
    """
    Decode and verify JWT token.
    Return None if token is invalid or expired.
    """

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        # Validate user ID
        if not payload.get("sub"):
            return None

        return payload

    except jwt.InvalidTokenError:
        return None
