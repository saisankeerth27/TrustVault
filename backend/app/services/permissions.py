"""Named-user document permission grants, updates, and revocation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.document_permission import DocumentPermission
from app.models.enums import AuditAction, AuditOutcome, PermissionLevel, UserStatus
from app.models.user import User
from app.services.audit import record_event
from app.services.auth import normalize_email

logger = logging.getLogger(__name__)


class PermissionRecipientNotFoundError(Exception):
    """Raised when a recipient email does not identify an active account."""


class PermissionRecipientIsOwnerError(Exception):
    """Raised when a document owner attempts to grant themselves access."""


class PermissionAlreadyExistsError(Exception):
    """Raised when a different active permission already exists."""


class PermissionNotFoundError(Exception):
    """Raised when an active permission cannot be found for a document."""


class PermissionOperationError(Exception):
    """Raised when a permission change cannot be committed."""


def _load_permission(session: Session, permission_id: UUID) -> DocumentPermission | None:
    return session.scalar(
        select(DocumentPermission)
        .where(DocumentPermission.id == permission_id)
        .options(selectinload(DocumentPermission.user))
    )


def _active_permission(
    session: Session,
    *,
    document_id: UUID,
    user_id: UUID,
    for_update: bool = False,
) -> DocumentPermission | None:
    statement = select(DocumentPermission).where(
        DocumentPermission.document_id == document_id,
        DocumentPermission.user_id == user_id,
        DocumentPermission.revoked_at.is_(None),
    )
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def grant_permission(
    session: Session,
    *,
    document: Document,
    recipient_email: str,
    permission: PermissionLevel,
    granted_by: User,
) -> tuple[DocumentPermission, bool]:
    """Grant READ/EDIT to an active registered user; return (record, created)."""

    recipient = session.scalar(
        select(User).where(User.email == normalize_email(recipient_email))
    )
    if recipient is None or recipient.status != UserStatus.ACTIVE.value:
        raise PermissionRecipientNotFoundError

    if recipient.id == document.owner_id:
        raise PermissionRecipientIsOwnerError

    existing = _active_permission(
        session,
        document_id=document.id,
        user_id=recipient.id,
        for_update=True,
    )
    if existing is not None:
        if existing.permission == permission.value:
            return existing, False
        raise PermissionAlreadyExistsError

    record = DocumentPermission(
        document_id=document.id,
        user_id=recipient.id,
        permission=permission.value,
        granted_by=granted_by.id,
    )
    session.add(record)

    try:
        session.flush()
        permission_id = record.id
        record_event(
            session,
            action=AuditAction.PERMISSION_GRANT,
            outcome=AuditOutcome.SUCCESS,
            actor=granted_by,
            document_id=document.id,
            details={
                "recipient_id": str(recipient.id),
                "permission": permission.value,
            },
        )
        session.commit()
    except IntegrityError as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after a permission conflict.")

        existing = _active_permission(
            session,
            document_id=document.id,
            user_id=recipient.id,
        )
        if existing is not None and existing.permission == permission.value:
            return existing, False
        raise PermissionAlreadyExistsError from exc
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after a permission grant error.")
        logger.error("Permission grant could not be committed.")
        raise PermissionOperationError("The permission could not be granted.") from exc

    loaded = _load_permission(session, permission_id)
    if loaded is None:
        raise PermissionOperationError("The permission could not be granted.")
    return loaded, True


def list_permissions(
    session: Session,
    *,
    document: Document,
) -> list[DocumentPermission]:
    return list(
        session.scalars(
            select(DocumentPermission)
            .where(DocumentPermission.document_id == document.id)
            .options(selectinload(DocumentPermission.user))
            .order_by(
                DocumentPermission.created_at.desc(),
                DocumentPermission.id.asc(),
            )
        ).all()
    )


def update_permission(
    session: Session,
    *,
    document: Document,
    permission_id: UUID,
    permission: PermissionLevel,
    updated_by: User,
) -> tuple[DocumentPermission, bool]:
    """Change an active grant by revoking it and recording the replacement."""

    existing = session.scalar(
        select(DocumentPermission)
        .where(
            DocumentPermission.id == permission_id,
            DocumentPermission.document_id == document.id,
            DocumentPermission.revoked_at.is_(None),
        )
        .with_for_update()
        .options(selectinload(DocumentPermission.user))
    )
    if existing is None:
        raise PermissionNotFoundError

    if existing.permission == permission.value:
        return existing, False

    replacement = DocumentPermission(
        document_id=document.id,
        user_id=existing.user_id,
        permission=permission.value,
        granted_by=updated_by.id,
    )
    existing.revoked_at = datetime.now(timezone.utc)
    session.add(replacement)

    try:
        session.flush()
        replacement_id = replacement.id
        record_event(
            session,
            action=AuditAction.PERMISSION_UPDATE,
            outcome=AuditOutcome.SUCCESS,
            actor=updated_by,
            document_id=document.id,
            details={
                "recipient_id": str(existing.user_id),
                "previous_permission": existing.permission,
                "permission": permission.value,
            },
        )
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after a permission update error.")
        logger.error("Permission update could not be committed.")
        raise PermissionOperationError("The permission could not be updated.") from exc

    loaded = _load_permission(session, replacement_id)
    if loaded is None:
        raise PermissionOperationError("The permission could not be updated.")
    return loaded, True


def revoke_permission(
    session: Session,
    *,
    document: Document,
    permission_id: UUID,
    revoked_by: User,
) -> bool:
    """Revoke a grant idempotently while retaining its history row."""

    record = session.scalar(
        select(DocumentPermission)
        .where(
            DocumentPermission.id == permission_id,
            DocumentPermission.document_id == document.id,
        )
        .with_for_update()
    )
    if record is None:
        raise PermissionNotFoundError

    if record.revoked_at is not None:
        return False

    record.revoked_at = datetime.now(timezone.utc)
    try:
        record_event(
            session,
            action=AuditAction.PERMISSION_REVOKE,
            outcome=AuditOutcome.SUCCESS,
            actor=revoked_by,
            document_id=document.id,
            details={
                "recipient_id": str(record.user_id),
                "permission": record.permission,
            },
        )
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after a permission revocation error.")
        logger.error("Permission revocation could not be committed.")
        raise PermissionOperationError("The permission could not be revoked.") from exc

    return True
