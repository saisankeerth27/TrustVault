from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenValidationError, decode_access_token
from app.db.session import get_db
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.services.auth import session_is_active

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def _unauthorized(message: str = "Not authenticated.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers=_UNAUTHORIZED_HEADERS,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        claims = decode_access_token(credentials.credentials)
    except TokenValidationError as exc:
        raise _unauthorized("Invalid or expired access token.") from exc

    user = session.get(User, claims.user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise _unauthorized("Invalid or expired access token.")

    if not session_is_active(
        session,
        user_id=user.id,
        family_id=claims.session_id,
    ):
        raise _unauthorized("Session is no longer active.")

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
