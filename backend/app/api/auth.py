from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import auth_rate_limiter
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth import (
    AccountExistsError,
    DisabledAccountError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
    authenticate,
    create_account,
    create_session_token,
    revoke_session,
    rotate_session,
)

logger = logging.getLogger("trustvault.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "trustvault_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"

_INVALID_CREDENTIALS = "Invalid email or password."
_INVALID_SESSION = "Session is invalid or has expired."


def _client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce_allowed_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().cors_origins:
        logger.warning("Rejected auth request from untrusted origin.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )


def _enforce_rate_limit(request: Request, keys: list[str]) -> None:
    settings = get_settings()
    retry_after = auth_rate_limiter.consume(
        keys,
        limit=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if retry_after is not None:
        logger.warning("Authentication rate limit exceeded.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.jwt_refresh_token_expire_days * 86_400,
        path=REFRESH_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _build_auth_response(user: User, session_id: UUID) -> AuthResponse:
    settings = get_settings()
    access_token = create_access_token(user.id, user.role, session_id)
    return AuthResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthResponse)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> AuthResponse:
    _enforce_allowed_origin(request)
    _enforce_rate_limit(request, [f"register:{_client_address(request)}"])

    try:
        user = create_account(
            session,
            name=payload.name,
            email=str(payload.email),
            password=payload.password.get_secret_value(),
            role=UserRole.VIEWER,
        )
    except AccountExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email cannot be created.",
        ) from exc

    refresh_plaintext, refresh_token = create_session_token(session, user)
    session.commit()

    _set_refresh_cookie(response, refresh_plaintext)
    _no_store(response)
    logger.info("Account registered user_id=%s role=%s", user.id, user.role)

    return _build_auth_response(user, refresh_token.family_id)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> AuthResponse:
    _enforce_allowed_origin(request)
    _enforce_rate_limit(
        request,
        [
            f"login-ip:{_client_address(request)}",
            f"login-email:{str(payload.email)}",
        ],
    )

    try:
        user = authenticate(
            session,
            email=str(payload.email),
            password=payload.password.get_secret_value(),
        )
    except DisabledAccountError as exc:
        logger.warning("Login rejected for disabled account.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_CREDENTIALS,
        ) from exc
    except InvalidCredentialsError as exc:
        logger.info("Login failed with invalid credentials.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_CREDENTIALS,
        ) from exc

    refresh_plaintext, refresh_token = create_session_token(session, user)
    session.commit()

    _set_refresh_cookie(response, refresh_plaintext)
    _no_store(response)
    logger.info("Login succeeded user_id=%s role=%s", user.id, user.role)

    return _build_auth_response(user, refresh_token.family_id)


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> AuthResponse:
    _enforce_allowed_origin(request)
    plaintext = request.cookies.get(REFRESH_COOKIE_NAME)

    if not plaintext:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_SESSION,
        )

    try:
        user, new_plaintext, refresh_token = rotate_session(
            session, plaintext=plaintext
        )
    except RefreshTokenReuseError as exc:
        session.commit()
        _clear_refresh_cookie(response)
        logger.warning("Refresh token reuse detected; session family revoked.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_SESSION,
        ) from exc
    except DisabledAccountError as exc:
        session.commit()
        _clear_refresh_cookie(response)
        logger.warning("Refresh rejected for disabled account.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_SESSION,
        ) from exc
    except InvalidRefreshTokenError as exc:
        session.commit()
        _clear_refresh_cookie(response)
        logger.info("Refresh failed with an invalid or expired token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_SESSION,
        ) from exc

    session.commit()

    _set_refresh_cookie(response, new_plaintext)
    _no_store(response)
    logger.info("Session refreshed user_id=%s", user.id)

    return _build_auth_response(user, refresh_token.family_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> None:
    _enforce_allowed_origin(request)
    plaintext = request.cookies.get(REFRESH_COOKIE_NAME)

    if plaintext:
        revoke_session(session, plaintext=plaintext)
        session.commit()
        logger.info("Logout completed; refresh session revoked.")

    _clear_refresh_cookie(response)
    _no_store(response)


@router.get("/me", response_model=UserResponse)
def read_current_user(
    response: Response,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    _no_store(response)
    return UserResponse.model_validate(current_user)
