from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_supabase_identity
from app.core.config import get_settings
from app.core.rate_limit import auth_rate_limiter, enforce_rate_limit
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.enums import AuditAction, AuditOutcome, UserRole, UserStatus
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    PasswordRecoveryRequest,
    PasswordRecoveryUpdateRequest,
    PasswordRecoveryVerifyRequest,
    RegisterRequest,
    UserResponse,
)
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
    normalize_email,
)
from app.services.supabase_auth import (
    SupabaseAuthError,
    get_user as get_supabase_user,
    request_password_recovery,
    update_recovery_password,
    verify_recovery_otp,
)

logger = logging.getLogger("trustvault.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "trustvault_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
RECOVERY_COOKIE_NAME = "trustvault_recovery"
RECOVERY_COOKIE_PATH = "/api/v1/auth/recovery/update-password"
RECOVERY_COOKIE_MAX_AGE = 600

_INVALID_CREDENTIALS = "Invalid email or password."
_INVALID_SESSION = "Session is invalid or has expired."


@router.post("/session", response_model=UserResponse)
def sync_supabase_session(
    identity: dict[str, object] = Depends(get_supabase_identity),
    session: Session = Depends(get_db),
) -> UserResponse:
    provider_id = identity.get("id")
    email = identity.get("email")
    if not isinstance(provider_id, str) or not isinstance(email, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase Auth identity.",
        )
    try:
        provider_uuid = UUID(provider_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase Auth identity.",
        ) from exc

    normalized_email = normalize_email(email)
    user = session.scalar(
        select(User)
        .where(User.supabase_auth_id == provider_uuid)
        .with_for_update()
    )
    if user is not None and user.email != normalized_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The authentication email does not match this TrustVault account.",
        )
    if user is None:
        user = session.scalar(
            select(User)
            .where(User.email == normalized_email)
            .with_for_update()
        )
    is_new_user = user is None
    if user is None:
        user_metadata = identity.get("user_metadata")
        metadata = user_metadata if isinstance(user_metadata, dict) else {}
        candidate_name = metadata.get("name")
        name = candidate_name.strip() if isinstance(candidate_name, str) else ""
        if not name or len(name) > 255:
            name = normalized_email.split("@", maxsplit=1)[0][:255]
        user = User(
            name=name,
            email=normalized_email,
            password_hash=None,
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The account could not be linked. Contact support.",
            ) from exc

    if user.status != UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is disabled.",
        )
    if user.supabase_auth_id not in (None, provider_uuid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is linked to a different authentication identity.",
        )

    user.supabase_auth_id = provider_uuid
    if is_new_user:
        _commit_with_success_audit(
            session,
            action=AuditAction.USER_REGISTERED,
            actor=user,
            details={
                "role": UserRole.USER.value,
                "resource_type": "USER",
                "target_user_id": str(user.id),
                "source": "supabase_auth",
            },
        )
    else:
        session.commit()
    return UserResponse.model_validate(user)


def _client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _reject_legacy_auth() -> None:
    if get_settings().app_env != "test":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Use Supabase Auth for registration, login, refresh, and logout.",
        )


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


def _set_recovery_cookie(response: Response, access_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=RECOVERY_COOKIE_NAME,
        value=access_token,
        max_age=RECOVERY_COOKIE_MAX_AGE,
        path=RECOVERY_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


def _clear_recovery_cookie(response: Response) -> dict[str, str]:
    settings = get_settings()
    response.delete_cookie(
        key=RECOVERY_COOKIE_NAME,
        path=RECOVERY_COOKIE_PATH,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
    return {"Set-Cookie": response.headers["set-cookie"]}


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


def _record_recovery_event(
    session: Session,
    *,
    action: AuditAction,
    outcome: AuditOutcome,
    actor: User | None = None,
    details: dict[str, object] | None = None,
) -> None:
    record_best_effort(
        session,
        action=action,
        outcome=outcome,
        actor=actor,
        details={"resource_type": "AUTH", **(details or {})},
    )


def _user_for_recovery_identity(
    session: Session,
    identity: dict[str, object],
) -> User | None:
    email = identity.get("email")
    provider_id = identity.get("id")
    if not isinstance(email, str) or not isinstance(provider_id, str):
        return None
    try:
        provider_uuid = UUID(provider_id)
    except ValueError:
        return None
    user = session.scalar(
        select(User).where(User.email == email.strip().lower())
    )
    if user is not None and user.supabase_auth_id not in (None, provider_uuid):
        return None
    return user


def _recovery_rate_limit(request: Request, email: str, *, verification: bool) -> None:
    email_key = f"password-recovery-email:{email}"
    ip_key = f"password-recovery-ip:{_client_address(request)}"
    enforce_rate_limit(
        auth_rate_limiter,
        [email_key, ip_key],
        limit=5 if verification else 3,
        window_seconds=900 if verification else 900,
        detail="Too many recovery attempts. Try again later.",
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
    _reject_legacy_auth()
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
    _reject_legacy_auth()
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
    _reject_legacy_auth()
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
    _reject_legacy_auth()
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


@router.post("/recovery/request")
def request_recovery(
    payload: PasswordRecoveryRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    _enforce_allowed_origin(request)
    _recovery_rate_limit(request, payload.email, verification=False)
    try:
        request_password_recovery(
            payload.email,
            get_settings().password_recovery_redirect_url,
        )
    except SupabaseAuthError as exc:
        _record_recovery_event(
            session,
            action=AuditAction.PASSWORD_RESET_REQUEST_FAILED,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "provider_error", "status_code": exc.status_code or 0},
        )
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        logger.warning("Supabase password recovery request failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password recovery is temporarily unavailable. Try again later.",
        ) from exc

    _record_recovery_event(
        session,
        action=AuditAction.PASSWORD_RESET_REQUESTED,
        outcome=AuditOutcome.SUCCESS,
        details={"request_status": "provider_accepted"},
    )
    return {
        "message": (
            "If an account exists for this email address, a verification code will be sent."
        )
    }


@router.post("/recovery/verify")
def verify_recovery(
    payload: PasswordRecoveryVerifyRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    _enforce_allowed_origin(request)
    _recovery_rate_limit(request, payload.email, verification=True)
    try:
        auth_result = verify_recovery_otp(payload.email, payload.token)
    except SupabaseAuthError as exc:
        _record_recovery_event(
            session,
            action=AuditAction.PASSWORD_RESET_VERIFICATION_FAILED,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "provider_rejected_or_unavailable"},
        )
        if exc.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many verification attempts. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        if exc.status_code is None or exc.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Code verification is temporarily unavailable. Try again later.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The code is invalid or expired. Check it and try again.",
        ) from exc

    access_token = auth_result.get("access_token")
    identity = auth_result.get("user")
    identity_email = identity.get("email") if isinstance(identity, dict) else None
    identity_id = identity.get("id") if isinstance(identity, dict) else None
    if (
        not isinstance(access_token, str)
        or not access_token
        or not isinstance(identity, dict)
        or not isinstance(identity_email, str)
        or identity_email.strip().lower() != payload.email
        or not isinstance(identity_id, str)
    ):
        _record_recovery_event(
            session,
            action=AuditAction.PASSWORD_RESET_VERIFICATION_FAILED,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "provider_response_invalid"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The code is invalid or expired. Check it and try again.",
        )

    actor = _user_for_recovery_identity(session, identity)
    details: dict[str, object] = {"verification": "recovery_otp"}
    if actor is not None:
        actor.supabase_auth_id = UUID(identity_id)
        details["target_user_id"] = str(actor.id)
    _record_recovery_event(
        session,
        action=AuditAction.PASSWORD_RESET_VERIFICATION_SUCCEEDED,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        details=details,
    )
    _set_recovery_cookie(response, access_token)
    _no_store(response)
    return {"message": "Email verified. You can now create a new password."}


@router.post("/recovery/update-password")
def update_recovery(
    payload: PasswordRecoveryUpdateRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    _enforce_allowed_origin(request)
    access_token = request.cookies.get(RECOVERY_COOKIE_NAME)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verify your email before updating your password.",
            headers=_clear_recovery_cookie(response),
        )

    try:
        identity = get_supabase_user(access_token)
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your recovery session has expired. Request a new code.",
            headers=_clear_recovery_cookie(response),
        ) from exc

    actor = _user_for_recovery_identity(session, identity)
    if actor is None or actor.status != UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account cannot update its password here.",
            headers=_clear_recovery_cookie(response),
        )

    try:
        update_recovery_password(access_token, payload.password.get_secret_value())
    except SupabaseAuthError as exc:
        _record_recovery_event(
            session,
            action=AuditAction.PASSWORD_UPDATE_FAILED,
            outcome=AuditOutcome.FAILURE,
            actor=actor,
            details={
                "target_user_id": str(actor.id),
                "reason": "provider_update_failed",
                "status_code": exc.status_code or 0,
            },
        )
        if exc.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many password update attempts. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        if exc.status_code is None or exc.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Password update is temporarily unavailable. Try again later.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The password could not be updated. Check the requirements and retry.",
        ) from exc

    _record_recovery_event(
        session,
        action=AuditAction.PASSWORD_CHANGED,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        details={
            "target_user_id": str(actor.id),
            "source": "verified_account_recovery",
        },
    )
    _clear_recovery_cookie(response)
    _no_store(response)
    return {"message": "Your password was updated. Sign in with your new password."}


@router.get("/me", response_model=UserResponse)
def read_current_user(
    response: Response,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    _no_store(response)
    return UserResponse.model_validate(current_user)
