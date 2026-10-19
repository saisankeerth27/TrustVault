"""Database URL normalization and pooler compatibility helpers."""

from sqlalchemy.engine import make_url

POSTGRES_DRIVERS = {"postgres", "postgresql"}


def normalize_database_url(database_url: str) -> str:
    """Return a SQLAlchemy URL that uses the psycopg 3 driver."""

    url = make_url(database_url)

    if url.drivername in POSTGRES_DRIVERS:
        url = url.set(drivername="postgresql+psycopg")

    return url.render_as_string(hide_password=False)


def is_transaction_pooler(database_url: str) -> bool:
    """Supabase transaction pooling should not use psycopg server-side prepares."""

    url = make_url(database_url)
    return url.port == 6543


def requires_ssl(database_url: str) -> bool:
    url = make_url(database_url)
    host = (url.host or "").lower()
    return host.endswith(".supabase.co") or host.endswith(".supabase.com")
