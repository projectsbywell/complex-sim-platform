"""JWT authentication and bcrypt password hashing (direct bcrypt, no passlib)."""
from __future__ import annotations

import datetime
import logging
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .config import settings

logger = logging.getLogger("complex_sim.auth")

_BCRYPT_MAX_BYTES = 72  # bcrypt hard limit; pre-truncate instead of crashing


def _bcrypt_bytes(password: str) -> bytes:
    data = password.encode("utf-8")
    if len(data) > _BCRYPT_MAX_BYTES:
        data = data[:_BCRYPT_MAX_BYTES]
    return data


def hash_password(password: str) -> str:
    """Hash a password with bcrypt (cost 12)."""
    return bcrypt.hashpw(
        _bcrypt_bytes(password), bcrypt.gensalt(rounds=12)
    ).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_bcrypt_bytes(password), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def create_access_token(username: str, role: str = "user") -> str:
    """Issue a signed HS256 JWT valid for ACCESS_TOKEN_EXPIRE_MINUTES."""
    now = datetime.datetime.now(datetime.timezone.utc)
    expire = now + datetime.timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": "complex-sim-platform",
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT; raises ``jose.JWTError`` on any failure."""
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            issuer="complex-sim-platform",
        )
    except TypeError:  # very old python-jose without issuer support
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_current_user(token: str = Depends(oauth2_scheme)):
    """Resolve the authenticated user from the Bearer token."""
    from .store import store  # local import to keep the module graph acyclic

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        username = payload.get("sub")
        if not username:
            raise credentials_error
    except JWTError:
        raise credentials_error
    user = store.get_user(username)
    if user is None:
        raise credentials_error
    return user


def require_admin(user=Depends(get_current_user)):
    """Dependency that only admits role=admin users."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user