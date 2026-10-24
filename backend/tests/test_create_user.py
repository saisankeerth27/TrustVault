from __future__ import annotations

from contextlib import AbstractContextManager
from types import SimpleNamespace
from uuid import UUID

from pydantic import SecretStr

from app.models.enums import UserRole
from scripts import create_user


class FakeSession(AbstractContextManager):
    def __init__(self) -> None:
        self.added = None
        self.committed = False

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def scalar(self, _statement: object) -> None:
        return None

    def add(self, user: object) -> None:
        self.added = user

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


def test_create_user_links_provider_identity_and_database_role(
    monkeypatch,
    capsys,
) -> None:
    session = FakeSession()
    auth_create_calls = []
    monkeypatch.setenv("TRUSTVAULT_USER_PASSWORD", "a strong password for admin")
    monkeypatch.setattr(
        create_user,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://project.supabase.co",
            supabase_service_role_key=SecretStr("server-only-key"),
        ),
    )
    monkeypatch.setattr(
        create_user,
        "get_session_factory",
        lambda: FakeSessionFactory(session),
    )
    monkeypatch.setattr(
        create_user,
        "_create_supabase_user",
        lambda *args, **kwargs: (
            auth_create_calls.append((args, kwargs))
            or UUID("7a537b40-faad-4531-b100-f501c3670a1a")
        ),
    )

    result = create_user.main(
        [
            "--email",
            "Admin@Example.com",
            "--name",
            "Admin User",
            "--role",
            UserRole.ADMINISTRATOR.value,
        ]
    )

    assert result == 0
    assert session.committed
    assert session.added.email == "admin@example.com"
    assert session.added.password_hash is None
    assert session.added.supabase_auth_id == UUID(
        "7a537b40-faad-4531-b100-f501c3670a1a"
    )
    assert session.added.role == UserRole.ADMINISTRATOR.value
    assert auth_create_calls[0][1]["email"] == "admin@example.com"
    assert auth_create_calls[0][1]["password"] == "a strong password for admin"
    assert "a strong password for admin" not in capsys.readouterr().out
