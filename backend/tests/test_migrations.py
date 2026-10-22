from alembic import command
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

    command.upgrade(config, "head")


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

    command.downgrade(config, "base")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        remaining_tables = set(inspect(engine).get_table_names())
        assert CORE_TABLES.isdisjoint(remaining_tables)
    finally:
        engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        assert CORE_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
