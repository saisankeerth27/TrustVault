from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.services.supabase_auth import SupabaseAuthError, get_user as get_supabase_user

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def _unauthorized(message: str = "Not authenticated.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers=_UNAUTHORIZED_HEADERS,
    )


def get_supabase_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        identity = get_supabase_user(credentials.credentials)
    except SupabaseAuthError as exc:
        if exc.status_code in (401, 403):
            raise _unauthorized("Invalid or expired access token.") from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable.",
        ) from exc

    user_metadata = identity.get("user_metadata")
    meta_verified = (
        user_metadata.get("email_verified")
        if isinstance(user_metadata, dict)
        else False
    )
    is_verified = bool(
        identity.get("email_confirmed_at")
        or identity.get("confirmed_at")
        or identity.get("email_verified")
        or meta_verified
    )
    if (
        not isinstance(identity.get("id"), str)
        or not isinstance(identity.get("email"), str)
        or not is_verified
    ):
        raise _unauthorized("A verified email address is required.")
    return identity


def get_current_user(
    identity: dict[str, Any] = Depends(get_supabase_identity),
    session: Session = Depends(get_db),
) -> User:
    supabase_id = identity.get("id")
    email = identity.get("email")
    if not isinstance(supabase_id, str) or not isinstance(email, str):
        raise _unauthorized("Invalid or expired access token.")
    try:
        provider_id = UUID(supabase_id)
    except ValueError as exc:
        raise _unauthorized("Invalid or expired access token.") from exc

    user = session.scalar(
        select(User).where(
            User.supabase_auth_id == provider_id,
            User.email == email.strip().lower(),
        )
    )
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise _unauthorized("Invalid or expired access token.")

    return user


def require_roles(*roles: UserRole | str) -> Callable[..., User]:
    """Create a dependency that requires one of the given trusted database roles."""

    if not roles:
        raise ValueError("At least one role is required.")

    allowed = {UserRole(role).value for role in roles}

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )
        return current_user

    return dependency


require_administrator = require_roles(UserRole.ADMINISTRATOR)
