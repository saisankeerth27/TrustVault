"""Lazy database engine and session management.

The engine is created only when a database-backed request or command actually
needs it, so importing the application does not require DATABASE_URL.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.url import (
    is_transaction_pooler,
    normalize_database_url,
    requires_ssl,
)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()

    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in the backend environment or .env file."
        )

    database_url = normalize_database_url(settings.database_url)
    connect_args: dict[str, object] = {}

    if is_transaction_pooler(database_url):
        connect_args["prepare_threshold"] = None

    if requires_ssl(database_url):
        connect_args["sslmode"] = "require"

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=1800,
        connect_args=connect_args,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that always closes its session."""

    factory = get_session_factory()
    with factory() as session:
        yield session
