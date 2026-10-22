from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document_permission import DocumentPermission
    from app.models.document_version import DocumentVersion
    from app.models.user import User


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_documents_name_not_blank"),
        CheckConstraint("file_size >= 0", name="ck_documents_file_size_nonnegative"),
        CheckConstraint(
            "storage_key LIKE 'documents/%'",
            name="ck_documents_storage_key_prefix",
        ),
        CheckConstraint(
            "storage_key NOT LIKE '%://%'",
            name="ck_documents_storage_key_not_url",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_documents_checksum_sha256",
        ),
        UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        Index("ix_documents_owner_id", "owner_id"),
        Index("ix_documents_category", "category"),
        Index("ix_documents_created_at", "created_at"),
        Index("ix_documents_owner_created_at", "owner_id", "created_at"),
        Index("ix_documents_category_created_at", "category", "created_at"),
        Index(
            "ix_documents_owner_active",
            "owner_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_documents_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_documents_owner_id_users"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    owner: Mapped[User] = relationship(
        back_populates="documents",
        foreign_keys=[owner_id],
    )
    permissions: Mapped[list[DocumentPermission]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def owner_name(self) -> str:
        return self.owner.name

    def __repr__(self) -> str:
        return f"Document(id={self.id!r}, name={self.name!r}, owner_id={self.owner_id!r})"
