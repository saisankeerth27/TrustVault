"""prevent document version number reuse

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "next_version_number",
            sa.Integer(),
            server_default=sa.text("2"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_documents_next_version_number_minimum",
        "documents",
        "next_version_number >= 2",
    )
    op.execute(
        """
        UPDATE documents
        SET next_version_number = GREATEST(
            COALESCE(
                (
                    SELECT MAX(document_versions.version_number)
                    FROM document_versions
                    WHERE document_versions.document_id = documents.id
                ),
                1
            ) + 1,
            2
        )
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_documents_next_version_number_minimum",
        "documents",
        type_="check",
    )
    op.drop_column("documents", "next_version_number")
