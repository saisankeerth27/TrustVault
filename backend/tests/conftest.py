import tempfile
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import embedded_postgres
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.rate_limit import (
    audit_integrity_rate_limiter,
    auth_rate_limiter,
    document_write_rate_limiter,
)
from app.db.session import get_db
from app.main import app
from tests.db_helpers import alembic_config

TEST_JWT_SECRET = "test-jwt-secret-for-trustvault-phase-three-0123456789"


@pytest.fixture(autouse=True)
def auth_test_settings(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS", "10")
    monkeypatch.setenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")
    get_settings.cache_clear()
    auth_rate_limiter.reset()
    document_write_rate_limiter.reset()
    audit_integrity_rate_limiter.reset()

    yield

    auth_rate_limiter.reset()
    document_write_rate_limiter.reset()
    audit_integrity_rate_limiter.reset()
    get_settings.cache_clear()


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


@pytest.fixture
def api_client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
