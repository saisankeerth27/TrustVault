from app.db.url import (
    is_transaction_pooler,
    normalize_database_url,
    requires_ssl,
)


def test_postgres_scheme_is_normalized_to_psycopg() -> None:
    assert normalize_database_url(
        "postgres://user:pass@example.com:5432/db"
    ) == "postgresql+psycopg://user:pass@example.com:5432/db"


def test_postgresql_scheme_is_normalized_to_psycopg() -> None:
    assert normalize_database_url(
        "postgresql://user:pass@example.com:5432/db"
    ) == "postgresql+psycopg://user:pass@example.com:5432/db"


def test_transaction_pooler_is_detected_by_port() -> None:
    assert is_transaction_pooler(
        "postgresql://user:pass@aws-0-region.pooler.supabase.com:6543/postgres"
    )
    assert not is_transaction_pooler(
        "postgresql://user:pass@db.example.supabase.co:5432/postgres"
    )


def test_supabase_hosts_require_ssl() -> None:
    assert requires_ssl("postgresql://user:pass@db.example.supabase.co:5432/postgres")
    assert requires_ssl(
        "postgresql://user:pass@aws-0-region.pooler.supabase.com:6543/postgres"
    )
    assert not requires_ssl("postgresql://postgres:postgres@127.0.0.1:5432/postgres")
