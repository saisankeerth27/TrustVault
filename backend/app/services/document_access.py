"""Centralized, database-backed document authorization policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.document_permission import DocumentPermission
from app.models.enums import (
    AuditAction,
    AuditOutcome,
    DocumentAccessLevel,
    PermissionLevel,
    UserRole,
    UserStatus,
)
from app.models.user import User
from app.services.audit import record_best_effort


class DocumentCapability(StrEnum):
    METADATA = "METADATA"
    READ = "READ"
    EDIT = "EDIT"
    DELETE = "DELETE"
    MANAGE_PERMISSIONS = "MANAGE_PERMISSIONS"


_DENIAL_ACTIONS = {
    DocumentCapability.METADATA: AuditAction.DOCUMENT_ACCESS_DENIED,
    DocumentCapability.READ: AuditAction.DOCUMENT_DOWNLOAD_DENIED,
    DocumentCapability.EDIT: AuditAction.DOCUMENT_EDIT_DENIED,
    DocumentCapability.DELETE: AuditAction.DOCUMENT_DELETE_DENIED,
    DocumentCapability.MANAGE_PERMISSIONS: AuditAction.PERMISSION_CHANGE_DENIED,
}


class DocumentNotFoundError(Exception):
    """Raised when a document is missing, deleted, or not visible to the caller."""


class DocumentAccessDeniedError(Exception):
    """Raised when a visible document does not permit the requested operation."""


@dataclass(frozen=True)
class AuthorizedDocument:
    document: Document
    access_level: DocumentAccessLevel


_ACCESS_CAPABILITIES: dict[DocumentAccessLevel, frozenset[DocumentCapability]] = {
    DocumentAccessLevel.OWNER: frozenset(
        {
            DocumentCapability.METADATA,
            DocumentCapability.READ,
            DocumentCapability.EDIT,
            DocumentCapability.DELETE,
            DocumentCapability.MANAGE_PERMISSIONS,
        }
    ),
    DocumentAccessLevel.EDIT: frozenset(
        {
            DocumentCapability.METADATA,
            DocumentCapability.READ,
            DocumentCapability.EDIT,
        }
    ),
    DocumentAccessLevel.READ: frozenset(
        {
            DocumentCapability.METADATA,
            DocumentCapability.READ,
        }
    ),
    DocumentAccessLevel.ADMINISTRATOR: frozenset({DocumentCapability.METADATA}),
}


def _active_grant_exists(user_id: UUID):
    return exists().where(
        DocumentPermission.document_id == Document.id,
        DocumentPermission.user_id == user_id,
        DocumentPermission.revoked_at.is_(None),
    )


def visible_document_scope(user: User) -> list:
    """Return SQL conditions limiting a user to owned or explicitly shared documents."""

    if user.role == UserRole.ADMINISTRATOR.value:
        return []
    return [
        or_(
            Document.owner_id == user.id,
            _active_grant_exists(user.id),
        )
    ]


def resolve_access_level(
    session: Session,
    *,
    user: User,
    document: Document,
) -> DocumentAccessLevel | None:
    """Resolve current access from ownership and active grants without caching."""

    if user.status != UserStatus.ACTIVE.value or document.deleted_at is not None:
        return None

    if document.owner_id == user.id:
        return DocumentAccessLevel.OWNER

    permission = session.scalar(
        select(DocumentPermission.permission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.user_id == user.id,
            DocumentPermission.revoked_at.is_(None),
        )
    )
    if permission is not None:
        try:
            return DocumentAccessLevel(PermissionLevel(permission).value)
        except ValueError:
            return None

    if user.role == UserRole.ADMINISTRATOR.value:
        return DocumentAccessLevel.ADMINISTRATOR

    return None


def _allows(access_level: DocumentAccessLevel | None, capability: DocumentCapability) -> bool:
    if access_level is None:
        return False
    return capability in _ACCESS_CAPABILITIES[access_level]


def can_read_document(
    session: Session,
    *,
    user: User,
    document: Document,
) -> bool:
    return _allows(
        resolve_access_level(session, user=user, document=document),
        DocumentCapability.READ,
    )


def can_edit_document(
    session: Session,
    *,
    user: User,
    document: Document,
) -> bool:
    return _allows(
        resolve_access_level(session, user=user, document=document),
        DocumentCapability.EDIT,
    )


def can_delete_document(
    session: Session,
    *,
    user: User,
    document: Document,
) -> bool:
    return _allows(
        resolve_access_level(session, user=user, document=document),
        DocumentCapability.DELETE,
    )


def can_manage_document_permissions(
    session: Session,
    *,
    user: User,
    document: Document,
) -> bool:
    return _allows(
        resolve_access_level(session, user=user, document=document),
        DocumentCapability.MANAGE_PERMISSIONS,
    )


def _record_access_denial(
    session: Session,
    *,
    user: User,
    document: Document | None,
    document_id: UUID,
    capability: DocumentCapability,
    reason: str,
    access_level: DocumentAccessLevel | None = None,
) -> None:
    details: dict[str, object] = {
        "attempted_document_id": str(document_id),
        "capability": capability.value,
        "reason": reason,
        "resource_type": "DOCUMENT",
    }
    if access_level is not None:
        details["access_level"] = access_level.value
    record_best_effort(
        session,
        action=_DENIAL_ACTIONS[capability],
        outcome=AuditOutcome.DENIED,
        actor=user,
        document_id=document.id if document is not None else None,
        details=details,
    )


def authorize_document(
    session: Session,
    *,
    user: User,
    document_id: UUID,
    capability: DocumentCapability,
) -> AuthorizedDocument:
    """Load an active document and enforce one capability at the server boundary."""

    document = session.scalar(
        select(Document)
        .where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
        .options(selectinload(Document.owner))
    )
    if document is None:
        _record_access_denial(
            session,
            user=user,
            document=None,
            document_id=document_id,
            capability=capability,
            reason="document_not_available",
        )
        raise DocumentNotFoundError

    access_level = resolve_access_level(session, user=user, document=document)
    if access_level is None:
        _record_access_denial(
            session,
            user=user,
            document=document,
            document_id=document_id,
            capability=capability,
            reason="not_visible",
        )
        raise DocumentNotFoundError
    if not _allows(access_level, capability):
        _record_access_denial(
            session,
            user=user,
            document=document,
            document_id=document_id,
            capability=capability,
            reason="insufficient_access",
            access_level=access_level,
        )
        raise DocumentAccessDeniedError

    document.access_level = access_level.value
    return AuthorizedDocument(document=document, access_level=access_level)


def annotate_access_levels(
    session: Session,
    *,
    user: User,
    documents: list[Document],
) -> None:
    """Attach the caller's effective access level to already-scoped documents."""

    if not documents:
        return

    document_ids = [document.id for document in documents]
    grants = {
        row[0]: row[1]
        for row in session.execute(
            select(
                DocumentPermission.document_id,
                DocumentPermission.permission,
            ).where(
                DocumentPermission.document_id.in_(document_ids),
                DocumentPermission.user_id == user.id,
                DocumentPermission.revoked_at.is_(None),
            )
        ).all()
    }

    for document in documents:
        if document.owner_id == user.id:
            level = DocumentAccessLevel.OWNER
        elif document.id in grants:
            try:
                level = DocumentAccessLevel(PermissionLevel(grants[document.id]).value)
            except ValueError:
                level = None
        elif user.role == UserRole.ADMINISTRATOR.value:
            level = DocumentAccessLevel.ADMINISTRATOR
        else:
            level = None

        if level is not None:
            document.access_level = level.value
