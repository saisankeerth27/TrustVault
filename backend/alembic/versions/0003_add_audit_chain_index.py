"""add audit chain index

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('audit_events', sa.Column('chain_index', sa.BigInteger(), nullable=True))
    op.execute(
        """
        WITH ordered AS (
            SELECT id, row_number() OVER (ORDER BY occurred_at ASC, id ASC) AS position
            FROM audit_events
        )
        UPDATE audit_events
        SET chain_index = ordered.position
        FROM ordered
        WHERE audit_events.id = ordered.id
        """
    )
    op.alter_column('audit_events', 'chain_index', existing_type=sa.BigInteger(), nullable=False)
    op.create_check_constraint(
        'ck_audit_events_chain_index_positive',
        'audit_events',
        'chain_index >= 1',
    )
    op.create_index(
        'ix_audit_events_chain_index',
        'audit_events',
        ['chain_index'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_audit_events_chain_index', table_name='audit_events')
    op.drop_constraint(
        'ck_audit_events_chain_index_positive',
        'audit_events',
        type_='check',
    )
    op.drop_column('audit_events', 'chain_index')
