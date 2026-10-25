"""Administrator-only account lifecycle rules."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import AuditAction, AuditOutcome, UserRole, UserStatus
from app.models.user import User
from app.services.audit import record_event
from app.services.auth import revoke_user_sessions
from app.services.supabase_auth import delete_supabase_user

logger = logging.getLogger(__name__)


class AdminAccountNotFoundError(Exception):
    """Raised when the requested account does not exist."""


class SelfAccountChangeError(Exception):
    """Raised when an administrator attempts to change their own access."""


class LastActiveAdministratorError(Exception):
    """Raised when an action would remove the final active administrator."""


class AdminAccountOperationError(Exception):
    """Raised when an account change cannot be committed."""


def _locked_user(session: Session, user_id: UUID) -> User:
    user = session.scalar(
        select(User).where(User.id == user_id).with_for_update()
    )
    if user is None:
        raise AdminAccountNotFoundError
    return user


def _active_administrator_count(session: Session, *, excluding: UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.ADMINISTRATOR.value,
                User.status == UserStatus.ACTIVE.value,
                User.id != excluding,
            )
        )
        or 0
    )


def _commit_account_change(
    session: Session,
    *,
    action: AuditAction,
    actor: User,
    target: User,
    details: dict[str, object],
) -> None:
    try:
        details["target_user_id"] = str(target.id)
        details["resource_type"] = "USER"
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
            logger.error("Database rollback failed after an account change error.")
        logger.error("Administrator account change could not be committed.")
        raise AdminAccountOperationError from exc


def update_account_status(
    session: Session,
    *,
    actor: User,
    target_user_id: UUID,
    status: UserStatus,
) -> tuple[User, bool]:
    target = _locked_user(session, target_user_id)
    if target.id == actor.id:
        raise SelfAccountChangeError
    if target.status == status.value:
        return target, False
    if (
        target.role == UserRole.ADMINISTRATOR.value
        and status == UserStatus.DISABLED
        and _active_administrator_count(session, excluding=target.id) == 0
    ):
        raise LastActiveAdministratorError

    previous_status = target.status
    target.status = status.value
    if status == UserStatus.DISABLED:
        revoke_user_sessions(session, user_id=target.id)

    _commit_account_change(
        session,
        action=AuditAction.USER_STATUS_CHANGED,
        actor=actor,
        target=target,
        details={
            "previous_status": previous_status,
            "status": target.status,
        },
    )
    session.refresh(target)
    return target, True


def update_account_role(
    session: Session,
    *,
    actor: User,
    target_user_id: UUID,
    role: UserRole,
) -> tuple[User, bool]:
    target = _locked_user(session, target_user_id)
    if target.id == actor.id:
        raise SelfAccountChangeError
    if target.role == role.value:
        return target, False
    if (
        target.role == UserRole.ADMINISTRATOR.value
        and target.status == UserStatus.ACTIVE.value
        and _active_administrator_count(session, excluding=target.id) == 0
    ):
        raise LastActiveAdministratorError

    previous_role = target.role
    target.role = role.value
    revoke_user_sessions(session, user_id=target.id)

    _commit_account_change(
        session,
        action=AuditAction.USER_ROLE_CHANGED,
        actor=actor,
        target=target,
        details={
            "previous_role": previous_role,
            "role": target.role,
        },
    )
    session.refresh(target)
    return target, True


def delete_account(
    session: Session,
    *,
    actor: User,
    target_user_id: UUID,
) -> None:
    target = _locked_user(session, target_user_id)
    if target.id == actor.id:
        raise SelfAccountChangeError
    if (
        target.role == UserRole.ADMINISTRATOR.value
        and target.status == UserStatus.ACTIVE.value
        and _active_administrator_count(session, excluding=target.id) == 0
    ):
        raise LastActiveAdministratorError

    target_email = target.email
    target_name = target.name
    supabase_auth_id = target.supabase_auth_id

    revoke_user_sessions(session, user_id=target.id)

    # Delete any documents owned by the target user
    owned_docs = session.scalars(
        select(Document).where(Document.owner_id == target.id)
    ).all()
    for doc in owned_docs:
        session.delete(doc)
    session.flush()

    _commit_account_change(
        session,
        action=AuditAction.USER_DELETED,
        actor=actor,
        target=target,
        details={
            "target_email": target_email,
            "target_name": target_name,
        },
    )

    refetched = session.get(User, target.id)
    if refetched is not None:
        session.delete(refetched)
        session.commit()

    if supabase_auth_id:
        delete_supabase_user(supabase_auth_id)

