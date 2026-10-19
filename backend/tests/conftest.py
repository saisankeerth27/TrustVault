import tempfile
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import embedded_postgres
import pytest
from alembic import command
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.db_helpers import alembic_config


@pytest.fixture(scope="session")
def postgres_server() -> Generator[embedded_postgres.PostgresServer, None, None]:
    pgdata = Path(tempfile.gettempdir()) / f"trustvault-pg-{uuid4().hex}"
    pgdata.mkdir(parents=True, exist_ok=True)

    server = embedded_postgres.get_server(str(pgdata), cleanup_mode="delete")
    server.ensure_pgdata_inited()
    server.ensure_postgres_running()
    server.psql("CREATE DATABASE trustvault_test;")
    server.psql("CREATE DATABASE trustvault_migration_test;")

    try:
        yield server
    finally:
        server.cleanup()


@pytest.fixture(scope="session")
def test_database_url(postgres_server: embedded_postgres.PostgresServer) -> str:
    database_url = postgres_server.get_uri("trustvault_test")
    command.upgrade(alembic_config(database_url), "head")
    return database_url


@pytest.fixture(scope="session")
def migration_database_url(postgres_server: embedded_postgres.PostgresServer) -> str:
    return postgres_server.get_uri("trustvault_migration_test")


@pytest.fixture(scope="session")
def engine(test_database_url: str) -> Generator[Engine, None, None]:
    test_engine = create_engine(test_database_url, poolclass=NullPool)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
