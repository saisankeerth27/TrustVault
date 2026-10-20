from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from tests.db_helpers import alembic_config

CORE_TABLES = {
    "users",
    "documents",
    "document_permissions",
    "audit_events",
    "refresh_tokens",
}


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
