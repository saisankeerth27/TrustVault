from alembic import command
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from tests.db_helpers import alembic_config

LEGACY_ROLES = {
    "legacy-owner@example.com": "DOCUMENT_OWNER",
    "legacy-viewer@example.com": "VIEWER",
    "legacy-admin@example.com": "ADMINISTRATOR",
}

CORE_TABLES = {
    "users",
    "documents",
    "document_permissions",
    "document_versions",
    "audit_events",
    "refresh_tokens",
}


def test_0004_migrates_legacy_roles_explicitly(migration_database_url: str) -> None:
    config = alembic_config(migration_database_url)
    command.upgrade(config, "0003")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            for email, role in LEGACY_ROLES.items():
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(name, email, password_hash, role, status) "
                        "VALUES (:name, :email, 'not-a-real-hash', :role, 'ACTIVE')"
                    ),
                    {
                        "name": email.split("@")[0],
                        "email": email,
                        "role": role,
                    },
                )
    finally:
        engine.dispose()

    command.upgrade(config, "0004")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            roles = dict(
                connection.execute(
                    text("SELECT email, role FROM users")
                ).all()
            )
            last_login_nullable = connection.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'users' AND column_name = 'last_login_at'"
                )
            ).scalar_one()
        indexes = {
            index["name"] for index in inspect(engine).get_indexes("users")
        }
    finally:
        engine.dispose()

    assert roles["legacy-owner@example.com"] == "USER"
    assert roles["legacy-viewer@example.com"] == "USER"
    assert roles["legacy-admin@example.com"] == "ADMINISTRATOR"
    assert last_login_nullable == "YES"
    assert {
        "ix_users_role",
        "ix_users_status",
        "ix_users_created_at",
    } <= indexes

    command.downgrade(config, "0003")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            downgraded = dict(
                connection.execute(
                    text("SELECT email, role FROM users")
                ).all()
            )
    finally:
        engine.dispose()

    assert downgraded["legacy-owner@example.com"] == "DOCUMENT_OWNER"
    assert downgraded["legacy-viewer@example.com"] == "DOCUMENT_OWNER"
    assert downgraded["legacy-admin@example.com"] == "ADMINISTRATOR"

    command.upgrade(config, "0008")


def test_0005_backfills_existing_documents_and_downgrades_cleanly(
    migration_database_url: str,
) -> None:
    config = alembic_config(migration_database_url)
    command.downgrade(config, "0004")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "INSERT INTO users "
                    "(name, email, password_hash, role, status) "
                    "VALUES ('Legacy Owner', 'legacy-version@example.com', "
                    "'not-a-real-hash', 'USER', 'ACTIVE') RETURNING id"
                )
            ).scalar_one()
            document_id = connection.execute(
                text(
                    "INSERT INTO documents "
                    "(owner_id, name, category, description, storage_key, "
                    "mime_type, file_size, checksum) "
                    "VALUES (:owner_id, 'Legacy report.pdf', 'Contracts', "
                    "'Existing document', 'documents/legacy/report.pdf', "
                    "'application/pdf', 2048, :checksum) RETURNING id"
                ),
                {"owner_id": user_id, "checksum": "d" * 64},
            ).scalar_one()
    finally:
        engine.dispose()

    command.upgrade(config, "0005")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            versions = connection.execute(
                text(
                    "SELECT document_id, version_number, storage_key, "
                    "original_filename, mime_type, file_size, checksum, "
                    "uploaded_by, change_summary, is_current "
                    "FROM document_versions"
                )
            ).mappings().all()
    finally:
        engine.dispose()

    assert len(versions) == 1
    version = versions[0]
    assert version["document_id"] == document_id
    assert version["version_number"] == 1
    assert version["storage_key"] == "documents/legacy/report.pdf"
    assert version["original_filename"] == "Legacy report.pdf"
    assert version["mime_type"] == "application/pdf"
    assert version["file_size"] == 2048
    assert version["checksum"] == "d" * 64
    assert version["uploaded_by"] == user_id
    assert version["change_summary"] == "Initial upload"
    assert version["is_current"] is True

    command.downgrade(config, "0004")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        inspector = inspect(engine)
        assert "document_versions" not in inspector.get_table_names()
        assert "documents" in inspector.get_table_names()
    finally:
        engine.dispose()

    command.upgrade(config, "0008")


def test_0007_backfills_next_version_number(
    migration_database_url: str,
) -> None:
    config = alembic_config(migration_database_url)
    command.downgrade(config, "0006")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "INSERT INTO users "
                    "(name, email, password_hash, role, status) "
                    "VALUES ('Sequence Owner', 'sequence@example.com', "
                    "'not-a-real-hash', 'USER', 'ACTIVE') RETURNING id"
                )
            ).scalar_one()
            document_id = connection.execute(
                text(
                    "INSERT INTO documents "
                    "(owner_id, name, category, description, storage_key, "
                    "mime_type, file_size, checksum) "
                    "VALUES (:owner_id, 'Sequence.pdf', 'Contracts', "
                    "'Sequence document', 'documents/sequence/v3.pdf', "
                    "'application/pdf', 2048, :checksum) RETURNING id"
                ),
                {"owner_id": user_id, "checksum": "f" * 64},
            ).scalar_one()
            for version_number, key in (
                (1, "documents/sequence/v1.pdf"),
                (3, "documents/sequence/v3.pdf"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO document_versions "
                        "(document_id, version_number, storage_key, "
                        "original_filename, mime_type, file_size, checksum, "
                        "uploaded_by, change_summary, is_current) "
                        "VALUES (:document_id, :version_number, :storage_key, "
                        "'Sequence.pdf', 'application/pdf', 1024, :checksum, "
                        ":uploaded_by, 'Revision', :is_current)"
                    ),
                    {
                        "document_id": document_id,
                        "version_number": version_number,
                        "storage_key": key,
                        "checksum": "a" * 64,
                        "uploaded_by": user_id,
                        "is_current": version_number == 3,
                    },
                )
    finally:
        engine.dispose()

    command.upgrade(config, "0007")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            next_version_number = connection.execute(
                text(
                    "SELECT next_version_number FROM documents "
                    "WHERE id = :document_id"
                ),
                {"document_id": document_id},
            ).scalar_one()
    finally:
        engine.dispose()

    assert next_version_number == 4
    command.upgrade(config, "0008")


def test_0009_links_supabase_identity_and_removes_legacy_password_hashes(
    migration_database_url: str,
) -> None:
    config = alembic_config(migration_database_url)
    command.upgrade(config, "0008")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(name, email, password_hash, role, status) "
                    "VALUES ('Supabase User', 'supabase-link@example.com', "
                    "'legacy-bcrypt-hash', 'USER', 'ACTIVE')"
                )
            )
    finally:
        engine.dispose()

    command.upgrade(config, "0009")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            password_hash = connection.execute(
                text(
                    "SELECT password_hash FROM users "
                    "WHERE email = 'supabase-link@example.com'"
                )
            ).scalar_one()
            columns = {
                column["name"]: column
                for column in inspect(engine).get_columns("users")
            }
        unique_constraints = {
            constraint["name"]
            for constraint in inspect(engine).get_unique_constraints("users")
        }
    finally:
        engine.dispose()

    assert password_hash is None
    assert columns["password_hash"]["nullable"] is True
    assert columns["supabase_auth_id"]["nullable"] is True
    assert "uq_users_supabase_auth_id" in unique_constraints

    with pytest.raises(RuntimeError, match="Migration 0009 is irreversible"):
        command.downgrade(config, "0008")


def test_migration_upgrade_check_and_downgrade(migration_database_url: str) -> None:
    config = alembic_config(migration_database_url)

    command.upgrade(config, "head")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        inspector = inspect(engine)
        assert CORE_TABLES <= set(inspector.get_table_names())

        permission_indexes = {
            index["name"]: index
            for index in inspector.get_indexes("document_permissions")
        }
        assert permission_indexes["uq_document_permissions_active"]["unique"] is True

        with engine.connect() as connection:
            extension = connection.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
            ).scalar_one()
            trigram_index = connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_documents_name_trgm'"
                )
            ).scalar_one()

        assert extension == "pg_trgm"
        assert "gin" in trigram_index.lower()
        assert "gin_trgm_ops" in trigram_index
    finally:
        engine.dispose()

    # Fails if the migration and SQLAlchemy metadata have drifted.
    command.check(config)

    with pytest.raises(RuntimeError, match="Migration 0009 is irreversible"):
        command.downgrade(config, "base")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        assert CORE_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
