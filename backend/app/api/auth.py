from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import auth_rate_limiter, enforce_rate_limit
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.enums import AuditAction, AuditOutcome, UserRole
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.audit import record_best_effort, record_event
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
    sec_fetch_site = request.headers.get("sec-fetch-site")
    origin = request.headers.get("origin")
    cors_origins = get_settings().cors_origins

    if sec_fetch_site == "cross-site":
        if not origin or origin not in cors_origins:
            logger.warning("Rejected cross-site auth request.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request origin is not allowed.",
            )

    if origin and origin not in cors_origins:
        logger.warning("Rejected auth request from untrusted origin.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )


def _enforce_rate_limit(request: Request, keys: list[str]) -> None:
    settings = get_settings()
    try:
        enforce_rate_limit(
            auth_rate_limiter,
            keys,
            limit=settings.auth_rate_limit_attempts,
            window_seconds=settings.auth_rate_limit_window_seconds,
            detail="Too many authentication attempts. Try again later.",
        )
    except HTTPException:
        logger.warning("Authentication rate limit exceeded.")
        raise


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


def _commit_with_success_audit(
    session: Session,
    *,
    action: AuditAction,
    actor: User | None,
    details: dict[str, object] | None = None,
) -> None:
    try:
        record_event(
            session,
            action=action,
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            details=details,
        )
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after an authentication audit error.")
        logger.error("Authentication action could not be committed with its audit event.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The request could not be completed.",
        ) from exc


def _record_login_failure(
    session: Session,
    *,
    reason: str,
    target_user_id: UUID | None = None,
) -> None:
    details: dict[str, object] = {
        "reason": reason,
        "resource_type": "USER",
    }
    if target_user_id is not None:
        details["target_user_id"] = str(target_user_id)
    record_best_effort(
        session,
        action=AuditAction.LOGIN_FAILURE,
        outcome=AuditOutcome.FAILURE,
        details=details,
    )


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
            role=UserRole.USER,
        )
    except AccountExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email cannot be created.",
        ) from exc

    refresh_plaintext, refresh_token = create_session_token(session, user)
    _commit_with_success_audit(
        session,
        action=AuditAction.USER_REGISTERED,
        actor=user,
        details={
            "role": user.role,
            "resource_type": "USER",
            "target_user_id": str(user.id),
        },
    )

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
        _record_login_failure(
            session,
            reason="disabled_account",
            target_user_id=exc.user_id,
        )
        logger.warning("Login rejected for disabled account.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_CREDENTIALS,
        ) from exc
    except InvalidCredentialsError as exc:
        _record_login_failure(
            session,
            reason="invalid_credentials",
            target_user_id=exc.user_id,
        )
        logger.info("Login failed with invalid credentials.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_CREDENTIALS,
        ) from exc

    refresh_plaintext, refresh_token = create_session_token(session, user)
    user.last_login_at = datetime.now(timezone.utc)
    _commit_with_success_audit(
        session,
        action=AuditAction.LOGIN_SUCCESS,
        actor=user,
        details={
            "role": user.role,
            "resource_type": "USER",
            "target_user_id": str(user.id),
        },
    )

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
        user_id = revoke_session(session, plaintext=plaintext)
        if user_id is not None:
            user = session.get(User, user_id)
            _commit_with_success_audit(
                session,
                action=AuditAction.LOGOUT,
                actor=user,
                details=None if user is not None else {"subject_user_id": str(user_id)},
            )
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
