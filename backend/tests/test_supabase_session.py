from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_supabase_identity
from app.models.enums import UserRole
from app.models.user import User
from tests.auth_helpers import DEFAULT_PASSWORD, register, unique_email


def test_verified_supabase_identity_links_existing_role_by_email(
    api_client: TestClient,
    db_session: Session,
) -> None:
    email = unique_email("supabase_link")
    registration = register(api_client, email=email)
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    user.role = UserRole.ADMINISTRATOR.value
    user.supabase_auth_id = None
    db_session.flush()

    response = api_client.post(
        "/api/v1/auth/session",
        headers={"Authorization": f"Bearer {registration.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == UserRole.ADMINISTRATOR.value
    assert user.supabase_auth_id == user.id
    assert user.password_hash is not None
    assert user.password_hash != DEFAULT_PASSWORD


def test_new_verified_supabase_account_never_receives_admin_role(
    api_client: TestClient,
    db_session: Session,
) -> None:
    email = unique_email("supabase_new")
    provider_id = "d96f6c9c-98c7-4f5b-9c77-0df0b4ee0001"
    api_client.app.dependency_overrides[get_supabase_identity] = lambda: {
        "id": provider_id,
        "email": email,
        "email_confirmed_at": "verified",
        "user_metadata": {"name": "New User", "role": "ADMINISTRATOR"},
    }

    response = api_client.post("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json()["role"] == UserRole.USER.value
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.password_hash is None
    assert str(user.supabase_auth_id) == provider_id
