"""deny direct PostgREST access to application tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-24

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_APPLICATION_TABLES = (
    "users",
    "refresh_tokens",
    "documents",
    "document_permissions",
    "document_versions",
    "audit_events",
)


def upgrade() -> None:
    for table in _APPLICATION_TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')

    op.execute(
        """
        REVOKE ALL ON TABLE
            public.users,
            public.refresh_tokens,
            public.documents,
            public.document_permissions,
            public.document_versions,
            public.audit_events
        FROM PUBLIC
        """
    )
    op.execute(
        """
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON TABLE
                    public.users,
                    public.refresh_tokens,
                    public.documents,
                    public.document_permissions,
                    public.document_versions,
                    public.audit_events
                FROM anon;
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'authenticated'
            ) THEN
                REVOKE ALL ON TABLE
                    public.users,
                    public.refresh_tokens,
                    public.documents,
                    public.document_permissions,
                    public.document_versions,
                    public.audit_events
                FROM authenticated;
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Keep explicit PUBLIC/PostgREST privilege revocations in place. Restoring
    # access without the original database grant policy could expose user data.
    for table in reversed(_APPLICATION_TABLES):
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
