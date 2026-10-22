"""Database-backed account and session services."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password_or_dummy,
)
from app.models.enums import UserRole, UserStatus
from app.models.refresh_token import RefreshToken
from app.models.user import User


class AccountExistsError(Exception):
    """Raised when an account with the normalized email already exists."""


class InvalidCredentialsError(Exception):
    """Raised for unknown accounts and wrong passwords."""

    def __init__(self, user_id: UUID | None = None) -> None:
        super().__init__("Invalid credentials.")
        self.user_id = user_id


class DisabledAccountError(InvalidCredentialsError):
    """Raised when valid credentials belong to a disabled account."""


class InvalidRefreshTokenError(Exception):
    """Raised when a refresh token is unknown, expired, or unusable."""


class RefreshTokenReuseError(InvalidRefreshTokenError):
    """Raised when an already-rotated refresh token is presented again."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_account(
    session: Session,
    *,
    name: str,
    email: str,
    password: str,
    role: UserRole,
) -> User:
    user = User(
        name=name.strip(),
        email=normalize_email(email),
        password_hash=hash_password(password),
        role=role.value,
        status=UserStatus.ACTIVE.value,
    )
    session.add(user)

    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise AccountExistsError from exc

    return user


def authenticate(
    session: Session,
    *,
    email: str,
    password: str,
) -> User:
    user = session.scalar(
        select(User).where(User.email == normalize_email(email))
    )
    password_matches = verify_password_or_dummy(
        password, user.password_hash if user else None
    )

    if user is None or not password_matches:
        raise InvalidCredentialsError(user.id if user is not None else None)

    if user.status != UserStatus.ACTIVE.value:
        raise DisabledAccountError(user.id)

    return user


def create_session_token(
    session: Session,
    user: User,
    *,
    family_id: UUID | None = None,
) -> tuple[str, RefreshToken]:
    plaintext = generate_refresh_token()
    refresh_token = RefreshToken(
        user_id=user.id,
        family_id=family_id or uuid4(),
        token_hash=hash_refresh_token(plaintext),
        expires_at=refresh_token_expiry(),
    )
    session.add(refresh_token)
    session.flush()
    return plaintext, refresh_token


def rotate_session(
    session: Session,
    *,
    plaintext: str,
) -> tuple[User, str, RefreshToken]:
    now = datetime.now(timezone.utc)
    refresh_token = session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(plaintext))
        .with_for_update()
    )

    if refresh_token is None:
        raise InvalidRefreshTokenError

    if refresh_token.revoked_at is not None:
        _revoke_family(session, refresh_token.family_id, now)
        raise RefreshTokenReuseError

    if refresh_token.expires_at <= now:
        refresh_token.revoked_at = now
        raise InvalidRefreshTokenError

    user = session.get(User, refresh_token.user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        _revoke_family(session, refresh_token.family_id, now)
        raise DisabledAccountError

    new_plaintext, new_token = create_session_token(
        session,
        user,
        family_id=refresh_token.family_id,
    )
    refresh_token.revoked_at = now
    refresh_token.replaced_by_id = new_token.id
    session.flush()

    return user, new_plaintext, new_token


def revoke_session(session: Session, *, plaintext: str) -> UUID | None:
    refresh_token = session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(plaintext))
        .with_for_update()
    )
    if refresh_token is None:
        return None

    user_id = refresh_token.user_id
    _revoke_family(
        session,
        refresh_token.family_id,
        datetime.now(timezone.utc),
    )
    return user_id


def session_is_active(
    session: Session,
    *,
    user_id: UUID,
    family_id: UUID,
) -> bool:
    active_token_id = session.scalar(
        select(RefreshToken.id)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .limit(1)
    )
    return active_token_id is not None


def revoke_user_sessions(
    session: Session,
    *,
    user_id: UUID,
    revoked_at: datetime | None = None,
) -> int:
    """Revoke every active refresh token for an account."""

    result = session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at or datetime.now(timezone.utc))
    )
    return int(result.rowcount or 0)


def _revoke_family(session: Session, family_id: UUID, revoked_at: datetime) -> None:
    session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=revoked_at)
    )
