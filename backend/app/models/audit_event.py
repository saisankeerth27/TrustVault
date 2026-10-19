from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('SUCCESS', 'DENIED', 'FAILURE')",
            name="ck_audit_events_outcome",
        ),
        CheckConstraint(
            "jsonb_typeof(details) = 'object'",
            name="ck_audit_events_details_object",
        ),
        CheckConstraint(
            "event_hash ~ '^[0-9a-f]{64}$'",
            name="ck_audit_events_event_hash_sha256",
        ),
        CheckConstraint(
            "previous_hash IS NULL OR previous_hash ~ '^[0-9a-f]{64}$'",
            name="ck_audit_events_previous_hash_sha256",
        ),
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_actor_id", "actor_id"),
        Index("ix_audit_events_document_id", "document_id"),
        Index("ix_audit_events_action", "action"),
        Index("ix_audit_events_outcome", "outcome"),
        Index("ix_audit_events_document_occurred", "document_id", "occurred_at"),
        Index("ix_audit_events_actor_occurred", "actor_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    actor_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_audit_events_actor_id_users",
        ),
        nullable=True,
    )
    document_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "documents.id",
            ondelete="SET NULL",
            name="fk_audit_events_document_id_documents",
        ),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    actor: Mapped[Optional[User]] = relationship(foreign_keys=[actor_id])
    document: Mapped[Optional[Document]] = relationship(foreign_keys=[document_id])

    def __repr__(self) -> str:
        return (
            f"AuditEvent(id={self.id!r}, action={self.action!r}, "
            f"outcome={self.outcome!r})"
        )
