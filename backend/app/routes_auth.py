"""Authentication routes: register, login (OAuth2 form), me."""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, field_validator

from .auth import create_access_token, get_current_user, hash_password, verify_password
from .config import settings
from .store import DuplicateUserError, store

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger("complex_sim.auth")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class RegisterRequest(BaseModel):
    """Anti-injection constraints: strict username charset, bounded length."""

    username: str = Field(..., min_length=3, max_length=32, description="3-32 chars, [A-Za-z0-9_.-]")
    password: str = Field(..., min_length=8, max_length=128, description="8-128 chars")

    @field_validator("username")
    @classmethod
    def _username_ok(cls, value: str) -> str:
        value = value.strip()
        if not USERNAME_RE.match(value):
            raise ValueError("username must match ^[A-Za-z0-9_.-]{3,32}$")
        return value


def _token_response(user) -> dict:
    return {
        "access_token": create_access_token(user.username, user.role),
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
    }


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a user and return a JWT access token",
    response_model=dict,
)
def register(req: RegisterRequest) -> dict:
    username = req.username
    if store.get_user(username) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    role = "admin" if username in settings.admin_users else "user"
    try:
        user = store.create_user(username, hash_password(req.password), role=role)
    except DuplicateUserError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    logger.info("user_registered", extra={"username": username, "role": role})
    return _token_response(user)


@router.post(
    "/login",
    summary="Login with username/password (OAuth2 password form)",
    response_model=dict,
)
def login(form: OAuth2PasswordRequestForm = Depends()) -> dict:
    user = store.get_user(form.username)
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info("user_login", extra={"username": user.username})
    return _token_response(user)


@router.get("/me", summary="Current user profile")
def me(user=Depends(get_current_user)) -> dict:
    return {
        "username": user.username,
        "role": user.role,
        "created_at": user.created_at,
    }