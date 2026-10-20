"""Password hashing and token primitives for TrustVault authentication."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import bcrypt
import jwt

from app.core.config import get_settings
from app.models.enums import UserRole

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_BYTES = 72
REFRESH_TOKEN_BYTES = 48
REFRESH_TOKEN_HASH_PREFIX = "sha256:"

_DUMMY_PASSWORD_HASH = (
    "$2b$12$9f6BJk8kKvb9KqOf8xwXJ.RG/SzVeVu6FfPw7iwN/EFLcvx4pxD3G"
)


class TokenValidationError(Exception):
    """Raised when an access token is missing, malformed, expired, or forged."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: UUID
    role: UserRole
    session_id: UUID


def validate_password_strength(password: str) -> None:
    """Validate a password without imposing composition rules that weaken entropy."""

    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
        )
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(
            f"Password must be at most {PASSWORD_MAX_BYTES} bytes when UTF-8 encoded."
        )


def hash_password(password: str) -> str:
    validate_password_strength(password)
    settings = get_settings()
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def verify_password_or_dummy(password: str, password_hash: str | None) -> bool:
    """Check a password with similar work for known and unknown accounts."""

    candidate_hash = password_hash or _DUMMY_PASSWORD_HASH
    matched = verify_password(password, candidate_hash)
    return matched and password_hash is not None


def create_access_token(
    user_id: UUID,
    role: str,
    session_id: UUID,
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    lifetime = expires_delta or timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "sid": str(session_id),
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + lifetime,
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        settings.require_jwt_secret(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> AccessTokenClaims:
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.require_jwt_secret(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "require": ["exp", "iat", "sub", "sid", "type", "iss", "aud"],
                "verify_signature": True,
            },
        )
    except jwt.InvalidTokenError as exc:
        raise TokenValidationError("Invalid or expired access token.") from exc

    if payload.get("type") != "access":
        raise TokenValidationError("Invalid access token type.")

    try:
        user_id = UUID(str(payload["sub"]))
        session_id = UUID(str(payload["sid"]))
        role = UserRole(str(payload["role"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenValidationError("Invalid access token claims.") from exc

    return AccessTokenClaims(user_id=user_id, role=role, session_id=session_id)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    # A prefixed, versioned hash keeps the lookup value unambiguous if the
    # algorithm changes in a future migration.
    return REFRESH_TOKEN_HASH_PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    settings = get_settings()
    return datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
