"""add document version history

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create immutable content versions and backfill existing documents."""
    op.create_table(
        "document_versions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column(
            "is_current",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version_number >= 1",
            name="ck_document_versions_number_positive",
        ),
        sa.CheckConstraint(
            "length(btrim(original_filename)) > 0",
            name="ck_document_versions_filename_not_blank",
        ),
        sa.CheckConstraint(
            "file_size >= 0",
            name="ck_document_versions_file_size_nonnegative",
        ),
        sa.CheckConstraint(
            "storage_key LIKE 'documents/%%'",
            name="ck_document_versions_storage_key_prefix",
        ),
        sa.CheckConstraint(
            "storage_key NOT LIKE '%%://%%'",
            name="ck_document_versions_storage_key_not_url",
        ),
        sa.CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_document_versions_checksum_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_versions_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name="fk_document_versions_uploaded_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_document_number",
        ),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_document_versions_storage_key",
        ),
    )
    op.create_index(
        "ix_document_versions_document_id",
        "document_versions",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_versions_uploaded_by",
        "document_versions",
        ["uploaded_by"],
        unique=False,
    )
    op.create_index(
        "ix_document_versions_created_at",
        "document_versions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "uq_document_versions_current",
        "document_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.execute(
        """
        INSERT INTO document_versions (
            document_id,
            version_number,
            storage_key,
            original_filename,
            mime_type,
            file_size,
            checksum,
            uploaded_by,
            change_summary,
            is_current,
            created_at
        )
        SELECT
            id,
            1,
            storage_key,
            name,
            mime_type,
            file_size,
            checksum,
            owner_id,
            'Initial upload',
            true,
            created_at
        FROM documents
        """
    )


def downgrade() -> None:
    """Remove version history without changing document current metadata."""
    op.drop_index(
        "uq_document_versions_current",
        table_name="document_versions",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_index(
        "ix_document_versions_created_at",
        table_name="document_versions",
    )
    op.drop_index(
        "ix_document_versions_uploaded_by",
        table_name="document_versions",
    )
    op.drop_index(
        "ix_document_versions_document_id",
        table_name="document_versions",
    )
    op.drop_table("document_versions")
