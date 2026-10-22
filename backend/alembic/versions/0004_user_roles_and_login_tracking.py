"""normalize user roles and add login tracking

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the two-role account model and login tracking."""
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.execute(
        """
        UPDATE users
        SET role = 'USER'
        WHERE role IN ('DOCUMENT_OWNER', 'VIEWER')
        """
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('ADMINISTRATOR', 'USER')",
    )

    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_status", "users", ["status"], unique=False)
    op.create_index("ix_users_created_at", "users", ["created_at"], unique=False)


def downgrade() -> None:
    """Restore the legacy role names without discarding accounts."""
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_role", table_name="users")

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.execute(
        """
        UPDATE users
        SET role = 'DOCUMENT_OWNER'
        WHERE role = 'USER'
        """
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('ADMINISTRATOR', 'DOCUMENT_OWNER', 'VIEWER')",
    )

    op.drop_column("users", "last_login_at")
