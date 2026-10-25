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
from app.models.audit_event import AuditEvent
from app.models.enums import AuditAction, AuditOutcome, UserRole, UserStatus
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    OtpLoginRequest,
    OtpVerifyRequest,
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
    create_user as create_supabase_user,
    find_user_by_email as find_supabase_user_by_email,
    get_user as get_supabase_user,
    is_email_confirmed as is_supabase_email_confirmed,
    request_password_recovery,
    sign_in_with_otp as supabase_sign_in_with_otp,
    sign_in_with_password,
    update_recovery_password,
    verify_otp_login as supabase_verify_otp_login,
    verify_recovery_otp,
    verify_signup_otp as supabase_verify_signup_otp,
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


def _registration_was_audited(session: Session, provider_uuid: UUID) -> bool:
    return (
        session.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.action == AuditAction.USER_REGISTERED.value,
                AuditEvent.outcome == AuditOutcome.SUCCESS.value,
                AuditEvent.details["provider_user_id"].as_string()
                == str(provider_uuid),
            )
            .limit(1)
        )
        is not None
    )


def _verified_identity_matches(
    identity: dict[str, object],
    expected_email: str,
) -> bool:
    email = identity.get("email")
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
    return (
        isinstance(email, str)
        and email.strip().lower() == expected_email.strip().lower()
        and is_verified
    )


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
    user.last_login_at = datetime.now(timezone.utc)
    if is_new_user and not _registration_was_audited(session, provider_uuid):
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


def _enforce_email_delivery_cooldown(email: str) -> None:
    """Match Supabase's per-address email cooldown before calling its API.

    Signup confirmation, confirmation resend, and password recovery all send
    email. Keeping one shared key avoids immediately re-submitting a request
    that Supabase would reject, without disclosing whether the address exists.
    """

    settings = get_settings()
    enforce_rate_limit(
        auth_rate_limiter,
        [f"auth-email-delivery:{email}"],
        limit=1,
        window_seconds=settings.auth_email_cooldown_seconds,
        detail="An email was already requested. Wait before requesting another one.",
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
    failure_detail: str = "The request could not be completed.",
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
            detail=failure_detail,
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


def _record_registration_failure(
    session: Session,
    *,
    reason: str,
    status_code: int = 0,
) -> None:
    record_best_effort(
        session,
        action=AuditAction.USER_REGISTERED,
        outcome=AuditOutcome.FAILURE,
        details={
            "reason": reason,
            "resource_type": "AUTH",
            "status_code": status_code,
        },
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


def _ensure_user_profile(
    session: Session,
    identity: dict[str, object],
    email: str,
    name: str,
) -> None:
    """Create or link an application User profile from a Supabase identity.

    Called during registration when Supabase creates the account but the
    email hasn't been confirmed yet.  The profile is committed with an
    audit record so that `sync_supabase_session` can find the user after
    the confirmation click.
    """
    provider_id = identity.get("id")
    if not isinstance(provider_id, str):
        return
    try:
        provider_uuid = UUID(provider_id)
    except ValueError:
        return

    normalized_email = normalize_email(email)
    user = session.scalar(
        select(User)
        .where(User.supabase_auth_id == provider_uuid)
        .with_for_update()
    )
    if user is None:
        user = session.scalar(
            select(User)
            .where(User.email == normalized_email)
            .with_for_update()
        )
    if user is None:
        candidate_name = name.strip() if isinstance(name, str) and name.strip() else None
        if not candidate_name or len(candidate_name) > 255:
            candidate_name = normalized_email.split("@", maxsplit=1)[0][:255]
        user = User(
            name=candidate_name,
            email=normalized_email,
            password_hash=None,
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return

    if user.supabase_auth_id is None:
        user.supabase_auth_id = provider_uuid

    if not _registration_was_audited(session, provider_uuid):
        _commit_with_success_audit(
            session,
            action=AuditAction.USER_REGISTERED,
            actor=None,
            details={
                "provider_user_id": str(provider_uuid),
                "request_status": "confirmation_pending",
                "resource_type": "AUTH",
                "source": "supabase_auth",
            },
            failure_detail=(
                "Supabase created the account, but TrustVault could not record "
                "the registration. Contact support before retrying."
            ),
        )
    else:
        session.commit()


_ALREADY_REGISTERED_MARKERS = (
    "already registered",
    "already been registered",
    "already exists",
    "user already exists",
    "user_already_exists",
    "email exists",
    "email_exists",
)


def _provider_says_already_registered(exc: SupabaseAuthError) -> bool:
    """Detect Supabase's "this account already exists" rejection."""

    message = (exc.provider_error or "").strip().lower()
    return bool(message) and any(
        marker in message for marker in _ALREADY_REGISTERED_MARKERS
    )


def _resend_signup_code(
    session: Session,
    *,
    email: str,
    provider_user: dict[str, object] | None,
) -> dict[str, object]:
    """Re-send the signup code for an existing unconfirmed account.

    Supabase refuses to create a second account for an address that already
    exists, even when that account was never confirmed. Re-sending the code
    through ``POST /otp`` keeps the user moving forward instead of trapping
    them in a permanent 400, and uses the project's *Magic Link* template so
    the 8-digit code and the link are both delivered.
    """

    try:
        supabase_sign_in_with_otp(
            email,
            get_settings().confirmation_redirect_url,
        )
    except SupabaseAuthError as exc:
        logger.warning(
            "Supabase confirmation resend rejected status=%s.",
            exc.status_code or 0,
        )
        _record_registration_failure(
            session,
            reason="confirmation_resend_failed",
            status_code=exc.status_code or 0,
        )
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many email requests. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        if exc.status_code is None or exc.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Registration is temporarily unavailable. Try again later.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This email is already registered. Sign in, or reset your "
                "password if you have forgotten it."
            ),
        ) from exc

    provider_id = (
        provider_user.get("id") if isinstance(provider_user, dict) else None
    )
    _commit_with_success_audit(
        session,
        action=AuditAction.USER_REGISTERED,
        actor=None,
        details={
            "provider_user_id": str(provider_id) if provider_id else None,
            "request_status": "confirmation_resent",
            "resource_type": "AUTH",
            "source": "supabase_auth",
        },
        failure_detail=(
            "Supabase accepted the confirmation resend, but TrustVault could "
            "not record it. Contact support before retrying."
        ),
    )
    return {
        "account_created": False,
        "requires_email_confirmation": True,
    }


@router.post("/supabase/register")
def register_with_supabase(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    _enforce_allowed_origin(request)
    _no_store(response)
    _enforce_rate_limit(
        request,
        [f"register-ip:{_client_address(request)}", f"register-email:{payload.email}"],
    )
    _enforce_email_delivery_cooldown(str(payload.email))

    normalized_email = normalize_email(payload.email)

    # A TrustVault profile is only a usable account when Supabase Auth also
    # holds the identity behind it, so both stores have to agree before we
    # tell someone their email is taken.
    existing_user = session.scalar(
        select(User).where(User.email == normalized_email)
    )

    try:
        provider_user = find_supabase_user_by_email(normalized_email)
        provider_checked = True
    except SupabaseAuthError as exc:
        logger.warning(
            "Supabase user lookup failed status=%s configuration_missing=%s.",
            exc.status_code or 0,
            exc.configuration_missing,
        )
        provider_user = None
        provider_checked = False

    if provider_user is not None:
        if is_supabase_email_confirmed(provider_user):
            _record_registration_failure(
                session,
                reason="email_already_registered",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This email is already registered. Sign in, or reset your "
                    "password if you have forgotten it."
                ),
            )
        # The provider holds an unconfirmed account for this address. Send the
        # signup code again instead of trying to create a duplicate.
        return _resend_signup_code(
            session,
            email=str(payload.email),
            provider_user=provider_user,
        )

    if existing_user is not None:
        if not provider_checked:
            # Never claim a profile is unusable (or recreate it) when the
            # provider could not be reached.
            _record_registration_failure(
                session,
                reason="provider_lookup_unavailable",
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Registration is temporarily unavailable. Try again later.",
            )
        # The local profile has no Supabase Auth identity behind it: a legacy
        # row or an account deleted outside TrustVault. Clear the stale link so
        # the new provider account can be linked once the emailed code is
        # verified, instead of reporting a false "already registered".
        if existing_user.supabase_auth_id is not None:
            existing_user.supabase_auth_id = None
            session.flush()
            logger.info(
                "Cleared stale Supabase link for local profile user_id=%s.",
                existing_user.id,
            )

    try:
        # Create the account with the submitted password but do not let
        # Supabase pick the template. ``admin/users`` sends nothing, so the
        # code below is delivered by ``POST /otp`` (the Magic Link template),
        # which carries both the 8-digit {{ .Token }} and {{ .ConfirmationURL }}.
        # The account stays unconfirmed until that code is verified.
        result = create_supabase_user(
            str(payload.email),
            payload.password.get_secret_value(),
            payload.name,
        )
    except SupabaseAuthError as exc:
        logger.warning(
            "Supabase user creation rejected status=%s configuration_missing=%s provider_error=%s.",
            exc.status_code or 0,
            exc.configuration_missing,
            exc.provider_error,
        )
        if exc.status_code in {
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        } and _provider_says_already_registered(exc):
            # The account appeared between our lookup and the create call, or
            # the provider did not disclose it through the admin API.
            try:
                provider_user = find_supabase_user_by_email(normalized_email)
            except SupabaseAuthError:
                provider_user = None
            if provider_user is not None and is_supabase_email_confirmed(
                provider_user
            ):
                _record_registration_failure(
                    session,
                    reason="email_already_registered",
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "This email is already registered. Sign in, or reset "
                        "your password if you have forgotten it."
                    ),
                ) from exc
            # Otherwise resend the code rather than trapping the user in a
            # permanent 400.
            return _resend_signup_code(
                session,
                email=str(payload.email),
                provider_user=provider_user,
            )
        _record_registration_failure(
            session,
            reason="provider_rejected_or_unavailable",
            status_code=exc.status_code or 0,
        )
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many registration attempts. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        if exc.status_code is None or exc.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Registration is temporarily unavailable. Try again later.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unable to create the account. {exc.provider_error or ''}"
                if exc.provider_error
                else (
                    "Unable to create the account. If you already have an account, "
                    "sign in or reset your password."
                )
            ),
        ) from exc

    # GoTrue may nest user data under "user" or return it at root level.
    provider_user = result.get("user") if isinstance(result.get("user"), dict) else result
    provider_id = provider_user.get("id") if isinstance(provider_user, dict) else None
    provider_email = provider_user.get("email") if isinstance(provider_user, dict) else None
    if (
        not isinstance(provider_id, str)
        or not isinstance(provider_email, str)
        or provider_email.strip().lower() != str(payload.email)
    ):
        _record_registration_failure(
            session,
            reason="provider_response_invalid",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable. Try again later.",
        )

    # The account exists but is unconfirmed. Issue the code/link now. If this
    # call fails the account remains unconfirmed, and a retry takes the
    # "unconfirmed provider account" branch above and resends it.
    try:
        supabase_sign_in_with_otp(
            str(payload.email),
            get_settings().confirmation_redirect_url,
        )
    except SupabaseAuthError as exc:
        logger.warning(
            "Supabase signup email rejected status=%s.", exc.status_code or 0
        )
        _record_registration_failure(
            session,
            reason="confirmation_send_failed",
            status_code=exc.status_code or 0,
        )
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many email requests. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable. Try again later.",
        ) from exc

    # Note: the TrustVault profile is NOT created here - it is created later
    # in verify_signup via sync_supabase_session once the OTP is validated.
    _commit_with_success_audit(
        session,
        action=AuditAction.USER_REGISTERED,
        actor=None,
        details={
            "provider_user_id": str(provider_id) if provider_id else None,
            "request_status": "confirmation_pending",
            "resource_type": "AUTH",
            "source": "supabase_auth",
        },
    )
    return {
        "account_created": True,
        "requires_email_confirmation": True,
    }


@router.post("/supabase/resend-confirmation")
def resend_confirmation_with_supabase(
    payload: PasswordRecoveryRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    """Ask Supabase to resend a signup email without disclosing account state."""

    _enforce_allowed_origin(request)
    _no_store(response)
    _enforce_rate_limit(
        request,
        [
            f"confirmation-resend-ip:{_client_address(request)}",
            f"confirmation-resend-email:{payload.email}",
        ],
    )
    _enforce_email_delivery_cooldown(str(payload.email))
    try:
        supabase_sign_in_with_otp(
            str(payload.email),
            get_settings().confirmation_redirect_url,
        )
    except SupabaseAuthError as exc:
        _record_registration_failure(
            session,
            reason="confirmation_resend_rejected_or_unavailable",
            status_code=exc.status_code or 0,
        )
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many confirmation requests. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        if exc.status_code is None or exc.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Confirmation email is temporarily unavailable. Try again later.",
            ) from exc

        # Supabase can reject requests for an already-confirmed or unknown
        # address.  Return the same generic result so this endpoint cannot be
        # used to discover which email addresses have TrustVault accounts.
        return {
            "message": (
                "If an account is awaiting confirmation, a new email will be sent."
            )
        }

    _commit_with_success_audit(
        session,
        action=AuditAction.USER_REGISTERED,
        actor=None,
        details={
            "resource_type": "AUTH",
            "request_status": "confirmation_resent",
            "source": "supabase_auth",
        },
    )
    return {
        "message": "If an account is awaiting confirmation, a new email will be sent."
    }


@router.post("/supabase/login")
def login_with_supabase(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    _enforce_allowed_origin(request)
    _no_store(response)
    _enforce_rate_limit(
        request,
        [
            f"login-ip:{_client_address(request)}",
            f"login-email:{str(payload.email)}",
        ],
    )
    try:
        result = sign_in_with_password(
            str(payload.email),
            payload.password.get_secret_value(),
        )
    except SupabaseAuthError as exc:
        _record_login_failure(session, reason="provider_rejected_or_unavailable")
        logger.warning(
            "Supabase password login failed status=%s.",
            exc.status_code or 0,
        )
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        if exc.status_code is None or exc.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Login is temporarily unavailable. Try again later.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_CREDENTIALS,
        ) from exc

    access_token = result.get("access_token")
    refresh_token = result.get("refresh_token")
    if not isinstance(access_token, str) or not access_token or not isinstance(
        refresh_token, str
    ) or not refresh_token:
        _record_login_failure(session, reason="provider_response_invalid")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login is temporarily unavailable. Try again later.",
        )

    try:
        identity = get_supabase_user(access_token)
        if not _verified_identity_matches(identity, str(payload.email)):
            raise SupabaseAuthError(401)
        user = sync_supabase_session(identity=identity, session=session)
    except SupabaseAuthError as exc:
        _record_login_failure(session, reason="provider_identity_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login is temporarily unavailable. Try again later.",
        ) from exc
    except HTTPException as exc:
        _record_login_failure(session, reason="trustvault_account_rejected")
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_CREDENTIALS,
            ) from exc
        raise

    actor = session.get(User, user.id)
    _commit_with_success_audit(
        session,
        action=AuditAction.LOGIN_SUCCESS,
        actor=actor,
        details={
            "role": user.role,
            "resource_type": "USER",
            "target_user_id": str(user.id),
            "source": "supabase_auth",
        },
    )
    return {
        "session": {
            "access_token": access_token,
            "refresh_token": refresh_token,
        },
        "user": user.model_dump(mode="json"),
    }


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
        failure_reason = (
            "missing_configuration" if exc.configuration_missing else "provider_error"
        )
        _record_recovery_event(
            session,
            action=AuditAction.PASSWORD_RESET_REQUEST_FAILED,
            outcome=AuditOutcome.FAILURE,
            details={
                "reason": failure_reason,
                "status_code": exc.status_code or 0,
            },
        )
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        if exc.configuration_missing:
            logger.error(
                "Supabase password recovery is unavailable because auth "
                "configuration is missing."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Password recovery is not configured. Set SUPABASE_URL and "
                    "SUPABASE_ANON_KEY in the backend environment, then restart it."
                ),
            ) from exc
        logger.warning(
            "Supabase password recovery request failed status=%s.",
            exc.status_code or 0,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password recovery is temporarily unavailable. Try again later.",
        ) from exc

    _commit_with_success_audit(
        session,
        action=AuditAction.PASSWORD_RESET_REQUESTED,
        actor=None,
        details={
            "resource_type": "AUTH",
            "request_status": "provider_accepted",
        },
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
        logger.warning(
            "Supabase recovery OTP verification failed status=%s.",
            exc.status_code or 0,
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

    try:
        provider_id = UUID(identity_id)
    except ValueError:
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
        actor.supabase_auth_id = provider_id
        details["target_user_id"] = str(actor.id)
    _commit_with_success_audit(
        session,
        action=AuditAction.PASSWORD_RESET_VERIFICATION_SUCCEEDED,
        actor=actor,
        details={"resource_type": "AUTH", **details},
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

    try:
        _commit_with_success_audit(
            session,
            action=AuditAction.PASSWORD_CHANGED,
            actor=actor,
            details={
                "resource_type": "AUTH",
                "target_user_id": str(actor.id),
                "source": "verified_account_recovery",
            },
            failure_detail=(
                "Supabase confirmed the password update, but TrustVault could not "
                "save its audit event. Contact an administrator before retrying."
            ),
        )
    except HTTPException as exc:
        headers = _clear_recovery_cookie(response)
        headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=headers,
        ) from exc
    _clear_recovery_cookie(response)
    _no_store(response)
    return {"message": "Your password was updated. Sign in with your new password."}


@router.post("/supabase/verify-signup")
def verify_signup(
    payload: OtpVerifyRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Verify a new account using the signup confirmation OTP from Supabase."""
    _enforce_allowed_origin(request)
    _enforce_rate_limit(
        request,
        [
            f"verify-signup-ip:{_client_address(request)}",
            f"verify-signup-email:{payload.email}",
        ],
    )
    try:
        auth_result = supabase_verify_signup_otp(payload.email, payload.token)
    except SupabaseAuthError as exc:
        logger.warning(
            "Signup OTP verification failed status=%s.", exc.status_code or 0
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
                detail="Verification is temporarily unavailable. Try again later.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The code is invalid or expired. Check it and try again.",
        ) from exc

    access_token = auth_result.get("access_token")
    refresh_token = auth_result.get("refresh_token")
    identity = auth_result.get("user")
    if (
        not isinstance(access_token, str)
        or not access_token
        or not isinstance(refresh_token, str)
        or not refresh_token
        or not isinstance(identity, dict)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The code is invalid or expired. Check it and try again.",
        )

    try:
        user = sync_supabase_session(identity=identity, session=session)
    except HTTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The code is invalid or expired. Check it and try again.",
        ) from exc

    return {
        "verified": True,
        "session": {
            "access_token": access_token,
            "refresh_token": refresh_token,
        },
        "user": user.model_dump(mode="json"),
    }


def _otp_rate_limit(request: Request, email: str, *, verification: bool) -> None:
    email_key = f"otp-login-email:{email}"
    ip_key = f"otp-login-ip:{_client_address(request)}"
    enforce_rate_limit(
        auth_rate_limiter,
        [email_key, ip_key],
        limit=5 if verification else 3,
        window_seconds=900,
        detail="Too many OTP attempts. Try again later.",
    )


@router.post("/otp/request")
def request_otp_login(
    payload: OtpLoginRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    """Send a passwordless sign-in OTP to the given email address.

    Only sends to email addresses that already have an active TrustVault account.
    Returns the same response regardless to avoid email enumeration.
    """
    _enforce_allowed_origin(request)
    _otp_rate_limit(request, payload.email, verification=False)
    _enforce_email_delivery_cooldown(str(payload.email))

    user = session.scalar(
        select(User).where(User.email == payload.email)
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is not registered. Please create a new TrustVault account.",
        )
    if user.status != UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not eligible for sign-in.",
        )

    try:
        supabase_sign_in_with_otp(payload.email)
    except SupabaseAuthError as exc:
        if exc.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Try again later.",
                headers={"Retry-After": "60"},
            ) from exc
        if exc.status_code is None or exc.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OTP login is temporarily unavailable. Try again later.",
            ) from exc
        logger.warning(
            "Supabase OTP request rejected for existing account status=%s.",
            exc.status_code or 0,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to send sign-in code. Please try again later.",
        ) from exc

    return {
        "message": "A one-time code has been sent to your email address."
    }


@router.post("/otp/verify")
def verify_otp_login(
    payload: OtpVerifyRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, object]:
    """Verify a passwordless sign-in OTP and return an authenticated session."""
    _enforce_allowed_origin(request)
    _otp_rate_limit(request, payload.email, verification=True)
    try:
        auth_result = supabase_verify_otp_login(payload.email, payload.token)
    except SupabaseAuthError as exc:
        logger.warning(
            "Passwordless OTP verification failed status=%s.", exc.status_code or 0
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
    refresh_token = auth_result.get("refresh_token")
    identity = auth_result.get("user")
    if (
        not isinstance(access_token, str)
        or not access_token
        or not isinstance(refresh_token, str)
        or not refresh_token
        or not isinstance(identity, dict)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The code is invalid or expired. Check it and try again.",
        )

    try:
        user = sync_supabase_session(identity=identity, session=session)
    except HTTPException as exc:
        _record_login_failure(session, reason="trustvault_account_rejected")
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_CREDENTIALS,
            ) from exc
        raise

    actor = session.get(User, user.id)
    _commit_with_success_audit(
        session,
        action=AuditAction.LOGIN_SUCCESS,
        actor=actor,
        details={
            "role": user.role,
            "resource_type": "USER",
            "target_user_id": str(user.id),
            "source": "otp_login",
        },
    )
    return {
        "session": {
            "access_token": access_token,
            "refresh_token": refresh_token,
        },
        "user": user.model_dump(mode="json"),
    }


@router.get("/me", response_model=UserResponse)
def read_current_user(
    response: Response,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    _no_store(response)
    return UserResponse.model_validate(current_user)
