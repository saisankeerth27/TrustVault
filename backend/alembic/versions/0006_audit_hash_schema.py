"""add versioned audit hash schema

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column(
            "hash_schema",
            sa.String(length=64),
            server_default=sa.text("'trustvault-audit-event-v1'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("audit_events", "hash_schema")
