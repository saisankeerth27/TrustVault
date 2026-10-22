from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
    from app.models.document import Document
    from app.models.user import User


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        CheckConstraint(
            "version_number >= 1",
            name="ck_document_versions_number_positive",
        ),
        CheckConstraint(
            "length(btrim(original_filename)) > 0",
            name="ck_document_versions_filename_not_blank",
        ),
        CheckConstraint(
            "file_size >= 0",
            name="ck_document_versions_file_size_nonnegative",
        ),
        CheckConstraint(
            "storage_key LIKE 'documents/%'",
            name="ck_document_versions_storage_key_prefix",
        ),
        CheckConstraint(
            "storage_key NOT LIKE '%://%'",
            name="ck_document_versions_storage_key_not_url",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_document_versions_checksum_sha256",
        ),
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_document_number",
        ),
        UniqueConstraint("storage_key", name="uq_document_versions_storage_key"),
        Index("ix_document_versions_document_id", "document_id"),
        Index("ix_document_versions_uploaded_by", "uploaded_by"),
        Index("ix_document_versions_created_at", "created_at"),
        Index(
            "uq_document_versions_current",
            "document_id",
            unique=True,
            postgresql_where=text("is_current"),
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
            name="fk_document_versions_document_id_documents",
        ),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_document_versions_uploaded_by_users",
        ),
        nullable=True,
    )
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[Document] = relationship(back_populates="versions")
    uploader: Mapped[Optional[User]] = relationship(foreign_keys=[uploaded_by])

    @property
    def uploader_name(self) -> str:
        return self.uploader.name if self.uploader is not None else "Former user"

    def __repr__(self) -> str:
        return (
            f"DocumentVersion(id={self.id!r}, document_id={self.document_id!r}, "
            f"version_number={self.version_number!r})"
        )
