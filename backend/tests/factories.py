from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.models.document_permission import DocumentPermission
from app.models.enums import (
    AuditAction,
    AuditOutcome,
    PermissionLevel,
    UserRole,
    UserStatus,
)
from app.models.user import User

VALID_SHA256 = "a" * 64


def user_kwargs(**overrides: object) -> dict[str, object]:
    suffix = uuid4().hex
    values: dict[str, object] = {
        "name": f"User {suffix[:8]}",
        "email": f"user-{suffix}@example.com",
        "password_hash": "not-a-real-hash",
        "role": UserRole.USER.value,
        "status": UserStatus.ACTIVE.value,
    }
    values.update(overrides)
    return values


def make_user(**overrides: object) -> User:
    return User(**user_kwargs(**overrides))


def document_kwargs(owner_id: object, **overrides: object) -> dict[str, object]:
    suffix = uuid4().hex
    values: dict[str, object] = {
        "owner_id": owner_id,
        "name": f"Document {suffix[:8]}",
        "category": "Contracts",
        "description": "Test document",
        "storage_key": f"documents/{suffix}/v1/file.pdf",
        "mime_type": "application/pdf",
        "file_size": 1024,
        "checksum": "b" * 64,
    }
    values.update(overrides)
    return values


def make_document(owner_id: object, **overrides: object) -> Document:
    return Document(**document_kwargs(owner_id, **overrides))


def make_permission(
    document_id: object,
    user_id: object,
    granted_by: object | None = None,
    permission: str = PermissionLevel.READ.value,
    revoked_at: datetime | None = None,
) -> DocumentPermission:
    return DocumentPermission(
        document_id=document_id,
        user_id=user_id,
        granted_by=granted_by,
        permission=permission,
        revoked_at=revoked_at,
    )


def make_audit_event(
    actor_id: object | None = None,
    document_id: object | None = None,
    action: str = AuditAction.DOCUMENT_ACCESS_DENIED.value,
    outcome: str = AuditOutcome.SUCCESS.value,
    details: dict[str, object] | None = None,
    event_hash: str = VALID_SHA256,
    previous_hash: str | None = None,
    chain_index: int = 1,
) -> AuditEvent:
    return AuditEvent(
        chain_index=chain_index,
        actor_id=actor_id,
        document_id=document_id,
        action=action,
        outcome=outcome,
        details=details or {},
        event_hash=event_hash,
        previous_hash=previous_hash,
    )
