from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
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
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class DocumentPermission(Base):
    __tablename__ = "document_permissions"
    __table_args__ = (
        CheckConstraint(
            "permission IN ('READ', 'EDIT')",
            name="ck_document_permissions_permission",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_document_permissions_revoked_after_created",
        ),
        Index("ix_document_permissions_document_id", "document_id"),
        Index("ix_document_permissions_user_id", "user_id"),
        Index(
            "uq_document_permissions_active",
            "document_id",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_document_permissions_active_user",
            "user_id",
            "document_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_document_permissions_history",
            "document_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
            name="fk_document_permissions_document_id_documents",
        ),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_document_permissions_user_id_users",
        ),
        nullable=False,
    )
    permission: Mapped[str] = mapped_column(String(8), nullable=False)
    granted_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_document_permissions_granted_by_users",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    document: Mapped[Document] = relationship(
        back_populates="permissions",
        foreign_keys=[document_id],
    )
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    granted_by_user: Mapped[Optional[User]] = relationship(foreign_keys=[granted_by])

    def __repr__(self) -> str:
        return (
            f"DocumentPermission(id={self.id!r}, document_id={self.document_id!r}, "
            f"user_id={self.user_id!r}, permission={self.permission!r})"
        )
