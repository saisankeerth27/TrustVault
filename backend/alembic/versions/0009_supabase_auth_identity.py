"""link TrustVault user records to Supabase Auth identities

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "supabase_auth_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_users_supabase_auth_id",
        "users",
        ["supabase_auth_id"],
    )
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.execute("UPDATE users SET password_hash = NULL")
    op.execute(
        "UPDATE refresh_tokens SET revoked_at = now() WHERE revoked_at IS NULL"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration 0009 is irreversible: cleared password hashes and revoked "
        "refresh sessions cannot be restored."
    )
