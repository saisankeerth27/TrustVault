from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth import create_account
from tests.auth_helpers import DEFAULT_PASSWORD, bearer, login, register, unique_email


def _token_for(api_client: TestClient, email: str) -> str:
    response = login(api_client, email=email)
    assert response.status_code == 200
    return response.json()["access_token"]


def test_role_dependency_returns_403_for_insufficient_privileges(
    api_client: TestClient, db_session: Session
) -> None:
    owner_email = unique_email("owner")
    admin_email = unique_email("admin")
    create_account(
        db_session,
        name="Owner User",
        email=owner_email,
        password=DEFAULT_PASSWORD,
        role=UserRole.DOCUMENT_OWNER,
    )
    create_account(
        db_session,
        name="Admin User",
        email=admin_email,
        password=DEFAULT_PASSWORD,
        role=UserRole.ADMINISTRATOR,
    )
    db_session.commit()

    viewer = register(api_client, email=unique_email("viewer"))
    viewer_token = viewer.json()["access_token"]
    owner_token = _token_for(api_client, owner_email)
    admin_token = _token_for(api_client, admin_email)

    admin_app = FastAPI()

    @admin_app.get("/admin-only")
    def admin_only(
        current_user: User = Depends(require_roles(UserRole.ADMINISTRATOR)),
    ) -> dict[str, str]:
        return {"user_id": str(current_user.id)}

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    admin_app.dependency_overrides[get_db] = override_get_db

    with TestClient(admin_app) as role_client:
        assert role_client.get("/admin-only").status_code == 401
        assert (
            role_client.get(
                "/admin-only", headers=bearer(viewer_token)
            ).status_code
            == 403
        )
        assert (
            role_client.get(
                "/admin-only", headers=bearer(owner_token)
            ).status_code
            == 403
        )
        allowed = role_client.get(
            "/admin-only", headers=bearer(admin_token)
        )
        assert allowed.status_code == 200

    me = api_client.get("/api/v1/auth/me", headers=bearer(viewer_token))
    assert me.status_code == 200
    assert me.json()["role"] == "VIEWER"


def test_me_uses_authenticated_identity_not_a_supplied_identifier(
    api_client: TestClient,
) -> None:
    first = register(api_client, email=unique_email("first"))
    second = register(api_client, email=unique_email("second"))
    first_id = first.json()["user"]["id"]
    second_id = second.json()["user"]["id"]

    response = api_client.get(
        f"/api/v1/auth/me?user_id={second_id}",
        headers=bearer(first.json()["access_token"]),
    )
    assert response.status_code == 200
    assert response.json()["id"] == first_id
    assert response.json()["id"] != second_id


def test_role_representation_matches_database_values() -> None:
    assert UserRole.ADMINISTRATOR.value == "ADMINISTRATOR"
    assert UserRole.DOCUMENT_OWNER.value == "DOCUMENT_OWNER"
    assert UserRole.VIEWER.value == "VIEWER"


def test_unknown_roles_fail_closed() -> None:
    with pytest.raises(ValueError):
        require_roles("SUPERUSER")
    with pytest.raises(ValueError):
        require_roles()
