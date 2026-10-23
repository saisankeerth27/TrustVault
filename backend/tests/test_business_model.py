from __future__ import annotations

import io
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.enums import UserRole, UserStatus
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.auth import create_account
from app.services.storage import get_storage_service
from tests.auth_helpers import DEFAULT_PASSWORD, bearer, login, register, unique_email

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[dict[str, object]] = []
        self.downloads: list[str] = []
        self.deletions: list[str] = []

    def upload_bytes(self, *, key: str, data: bytes, content_type: str) -> None:
        self.uploads.append({"key": key, "data": data, "content_type": content_type})

    def open_download(self, *, key: str):
        self.downloads.append(key)
        return io.BytesIO(PDF_BYTES)

    def delete_object(self, *, key: str) -> None:
        self.deletions.append(key)


@pytest.fixture
def fake_storage(api_client: TestClient):
    storage = FakeStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        yield storage
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


def _create_account(
    db_session: Session,
    *,
    role: UserRole = UserRole.USER,
    name: str = "Business User",
) -> tuple[str, User]:
    email = unique_email(role.value.lower())
    user = create_account(
        db_session,
        name=name,
        email=email,
        password=DEFAULT_PASSWORD,
        role=role,
    )
    db_session.commit()
    return email, user


def _token_for(api_client: TestClient, email: str) -> str:
    response = login(api_client, email=email)
    assert response.status_code == 200
    return response.json()["access_token"]


def _upload(api_client: TestClient, token: str, *, name: str = "Business.pdf") -> dict:
    response = api_client.post(
        "/api/v1/documents/upload",
        headers=bearer(token),
        files={"file": (name, PDF_BYTES, "application/pdf")},
        data={"category": "Business", "description": "Business model test"},
    )
    assert response.status_code == 201
    return response.json()


def _grant(
    api_client: TestClient,
    token: str,
    document_id: str,
    email: str,
    permission: str = "READ",
):
    return api_client.post(
        f"/api/v1/documents/{document_id}/permissions",
        headers=bearer(token),
        json={"email": email, "permission": permission},
    )


def test_normal_users_upload_and_only_see_their_own_documents(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    first_email, first = _create_account(db_session, name="First Owner")
    second_email, second = _create_account(db_session, name="Second Owner")
    first_token = _token_for(api_client, first_email)
    second_token = _token_for(api_client, second_email)

    first_document = _upload(api_client, first_token, name="First.pdf")
    second_document = _upload(api_client, second_token, name="Second.pdf")

    assert "owner_id" not in first_document
    assert "owner_id" not in second_document
    assert first_document["access_level"] == "OWNER"
    assert second_document["access_level"] == "OWNER"

    first_list = api_client.get("/api/v1/documents", headers=bearer(first_token)).json()
    second_list = api_client.get("/api/v1/documents", headers=bearer(second_token)).json()
    assert {item["id"] for item in first_list["items"]} == {first_document["id"]}
    assert {item["id"] for item in second_list["items"]} == {second_document["id"]}
    assert api_client.get(
        f"/api/v1/documents/{second_document['id']}",
        headers=bearer(first_token),
    ).status_code == 404
    assert len(fake_storage.uploads) == 2


def test_read_and_edit_grants_enforce_document_level_capabilities(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, owner = _create_account(db_session, name="Document Owner")
    recipient_email, recipient = _create_account(db_session, name="Recipient")
    owner_token = _token_for(api_client, owner_email)
    recipient_token = _token_for(api_client, recipient_email)
    document = _upload(api_client, owner_token)

    assert _grant(
        api_client, owner_token, document["id"], recipient_email, "READ"
    ).status_code == 201

    recipient_list = api_client.get(
        "/api/v1/documents", headers=bearer(recipient_token)
    ).json()
    assert [item["id"] for item in recipient_list["items"]] == [document["id"]]
    assert recipient_list["items"][0]["access_level"] == "READ"
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(recipient_token),
    ).status_code == 200
    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(recipient_token),
        json={"name": "READ cannot edit.pdf"},
    ).status_code == 403
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(recipient_token),
    ).status_code == 403
    assert _grant(
        api_client, recipient_token, document["id"], owner_email, "EDIT"
    ).status_code == 403

    permission_id = api_client.get(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
    ).json()["items"][0]["id"]
    assert api_client.patch(
        f"/api/v1/documents/{document['id']}/permissions/{permission_id}",
        headers=bearer(owner_token),
        json={"permission": "EDIT"},
    ).status_code == 200

    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(recipient_token),
        json={"name": "EDIT can rename.pdf"},
    ).status_code == 200
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(recipient_token),
    ).status_code == 403
    assert _grant(
        api_client, recipient_token, document["id"], owner_email, "READ"
    ).status_code == 403
    assert fake_storage.deletions == []
    assert recipient.id != owner.id


def test_permission_revocation_is_immediate_and_audited(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_account(db_session, name="Revoking Owner")
    recipient_email, recipient = _create_account(db_session, name="Revoked Recipient")
    owner_token = _token_for(api_client, owner_email)
    recipient_token = _token_for(api_client, recipient_email)
    document = _upload(api_client, owner_token)

    grant = _grant(api_client, owner_token, document["id"], recipient_email, "EDIT")
    assert grant.status_code == 201
    permission_id = grant.json()["id"]
    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(recipient_token),
    ).status_code == 200

    assert api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{permission_id}",
        headers=bearer(owner_token),
    ).status_code == 204
    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(recipient_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(recipient_token),
    ).status_code == 404

    events = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(_token_for(api_client, _create_account(
            db_session, role=UserRole.ADMINISTRATOR
        )[0])),
        params={"target_user_id": str(recipient.id)},
    )
    assert events.status_code == 200
    actions = {item["action"] for item in events.json()["items"]}
    assert {"PERMISSION_GRANT", "PERMISSION_REVOKE"} <= actions


def test_normal_user_cannot_access_administrator_oversight(
    api_client: TestClient,
    db_session: Session,
) -> None:
    email, user = _create_account(db_session)
    token = _token_for(api_client, email)

    for path in (
        "/api/v1/admin/users",
        "/api/v1/admin/summary",
        "/api/v1/admin/audit-events",
    ):
        response = api_client.get(path, headers=bearer(token))
        assert response.status_code == 403

    self_promotion = api_client.patch(
        f"/api/v1/admin/users/{user.id}/role",
        headers=bearer(token),
        json={"role": "ADMINISTRATOR"},
    )
    assert self_promotion.status_code == 403


def test_admin_lists_accounts_with_last_login_and_filters(
    api_client: TestClient,
    db_session: Session,
) -> None:
    admin_email, admin = _create_account(
        db_session,
        role=UserRole.ADMINISTRATOR,
        name="Oversight Admin",
    )
    target_email, target = _create_account(db_session, name="Searchable Tester")
    _token_for(api_client, target_email)
    admin_token = _token_for(api_client, admin_email)

    response = api_client.get(
        "/api/v1/admin/users",
        headers=bearer(admin_token),
        params={"q": "Searchable", "status": "ACTIVE", "role": "USER"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["id"] == str(target.id)
    assert item["email"] == target_email
    assert item["role"] == "USER"
    assert item["status"] == "ACTIVE"
    assert item["last_login_at"] is not None
    assert item["document_count"] == 0
    assert item["id"] != str(admin.id)


def test_admin_summary_reflects_real_data(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    admin_email, _ = _create_account(
        db_session,
        role=UserRole.ADMINISTRATOR,
    )
    owner_email, _ = _create_account(db_session)
    admin_token = _token_for(api_client, admin_email)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    summary = api_client.get(
        "/api/v1/admin/summary", headers=bearer(admin_token)
    )
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_users"] == 2
    assert payload["active_users"] == 2
    assert payload["disabled_users"] == 0
    assert payload["administrators"] == 1
    assert payload["normal_users"] == 1
    assert payload["active_documents"] == 1
    assert payload["active_grants"] == 0

    _grant(api_client, owner_token, document["id"], admin_email, "READ")
    summary = api_client.get(
        "/api/v1/admin/summary", headers=bearer(admin_token)
    ).json()
    assert summary["active_grants"] == 1


def test_admin_can_disable_and_reactivate_an_account(
    api_client: TestClient,
    db_session: Session,
) -> None:
    admin_email, _ = _create_account(
        db_session,
        role=UserRole.ADMINISTRATOR,
    )
    user_email, user = _create_account(db_session)
    admin_token = _token_for(api_client, admin_email)
    user_token = _token_for(api_client, user_email)

    disabled = api_client.patch(
        f"/api/v1/admin/users/{user.id}/status",
        headers=bearer(admin_token),
        json={"status": "DISABLED"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["changed"] is True
    assert disabled.json()["user"]["status"] == "DISABLED"

    db_session.expire_all()
    tokens = list(
        db_session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        ).all()
    )
    assert tokens
    assert all(token.revoked_at is not None for token in tokens)

    assert api_client.get(
        "/api/v1/documents", headers=bearer(user_token)
    ).status_code == 401
    assert login(api_client, email=user_email).status_code == 401

    reactivated = api_client.patch(
        f"/api/v1/admin/users/{user.id}/status",
        headers=bearer(admin_token),
        json={"status": "ACTIVE"},
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["changed"] is True
    assert reactivated.json()["user"]["status"] == "ACTIVE"
    assert login(api_client, email=user_email).status_code == 200


def test_admin_cannot_disable_or_change_own_role(
    api_client: TestClient,
    db_session: Session,
) -> None:
    admin_email, admin = _create_account(
        db_session,
        role=UserRole.ADMINISTRATOR,
    )
    admin_token = _token_for(api_client, admin_email)

    disable_self = api_client.patch(
        f"/api/v1/admin/users/{admin.id}/status",
        headers=bearer(admin_token),
        json={"status": "DISABLED"},
    )
    role_self = api_client.patch(
        f"/api/v1/admin/users/{admin.id}/role",
        headers=bearer(admin_token),
        json={"role": "USER"},
    )
    assert disable_self.status_code == 409
    assert role_self.status_code == 409

    events = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"target_user_id": str(admin.id), "resource_type": "USER"},
    ).json()["items"]
    denied = [
        item
        for item in events
        if item["outcome"] == "DENIED"
        and item["action"] in {"USER_STATUS_CHANGED", "USER_ROLE_CHANGED"}
    ]
    assert {item["action"] for item in denied} == {
        "USER_STATUS_CHANGED",
        "USER_ROLE_CHANGED",
    }
    assert all(item["target_user_id"] == str(admin.id) for item in denied)


def test_admin_role_change_is_audited_and_revokes_target_sessions(
    api_client: TestClient,
    db_session: Session,
) -> None:
    admin_email, _ = _create_account(
        db_session,
        role=UserRole.ADMINISTRATOR,
    )
    user_email, user = _create_account(db_session)
    admin_token = _token_for(api_client, admin_email)
    user_token = _token_for(api_client, user_email)

    promoted = api_client.patch(
        f"/api/v1/admin/users/{user.id}/role",
        headers=bearer(admin_token),
        json={"role": "ADMINISTRATOR"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["user"]["role"] == "ADMINISTRATOR"

    assert api_client.get(
        "/api/v1/admin/users", headers=bearer(user_token)
    ).status_code == 401
    new_admin_token = _token_for(api_client, user_email)
    assert api_client.get(
        "/api/v1/admin/users", headers=bearer(new_admin_token)
    ).status_code == 200

    events = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={
            "target_user_id": str(user.id),
            "resource_type": "USER",
        },
    )
    assert events.status_code == 200
    event = next(
        item
        for item in events.json()["items"]
        if item["action"] == "USER_ROLE_CHANGED"
    )
    assert event["details"]["previous_role"] == "USER"
    assert event["details"]["role"] == "ADMINISTRATOR"
    assert event["target_user_id"] == str(user.id)


def test_account_status_and_role_audit_have_explicit_targets(
    api_client: TestClient,
    db_session: Session,
) -> None:
    admin_email, _ = _create_account(
        db_session,
        role=UserRole.ADMINISTRATOR,
    )
    user_email, user = _create_account(db_session)
    admin_token = _token_for(api_client, admin_email)

    assert api_client.patch(
        f"/api/v1/admin/users/{user.id}/status",
        headers=bearer(admin_token),
        json={"status": "DISABLED"},
    ).status_code == 200
    assert api_client.patch(
        f"/api/v1/admin/users/{user.id}/status",
        headers=bearer(admin_token),
        json={"status": "ACTIVE"},
    ).status_code == 200

    events = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"target_user_id": str(user.id), "resource_type": "USER"},
    ).json()["items"]
    status_events = [
        item for item in events if item["action"] == "USER_STATUS_CHANGED"
    ]
    assert len(status_events) == 2
    assert all(item["target_user_id"] == str(user.id) for item in status_events)
    assert status_events[0]["details"]["status"] in {"ACTIVE", "DISABLED"}


def test_admin_can_review_metadata_and_grants_but_not_content(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    admin_email, _ = _create_account(
        db_session,
        role=UserRole.ADMINISTRATOR,
    )
    owner_email, owner = _create_account(db_session)
    recipient_email, recipient = _create_account(db_session)
    admin_token = _token_for(api_client, admin_email)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)
    assert _grant(
        api_client, owner_token, document["id"], recipient_email, "READ"
    ).status_code == 201

    all_documents = api_client.get(
        "/api/v1/documents", headers=bearer(admin_token)
    ).json()
    assert [item["id"] for item in all_documents["items"]] == [document["id"]]
    assert all_documents["items"][0]["access_level"] == "ADMINISTRATOR"
    assert "owner_id" not in all_documents["items"][0]
    assert all_documents["items"][0]["owner_name"] == owner.name

    permissions = api_client.get(
        f"/api/v1/admin/documents/{document['id']}/permissions",
        headers=bearer(admin_token),
    )
    assert permissions.status_code == 200
    assert permissions.json()["active_total"] == 1
    assert permissions.json()["items"][0]["user_id"] == str(recipient.id)

    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(admin_token),
    ).status_code == 403
    assert fake_storage.downloads == []


def test_owner_can_manage_shares_without_admin_approval(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_account(db_session)
    recipient_email, _ = _create_account(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    grant = _grant(api_client, owner_token, document["id"], recipient_email, "READ")
    permissions = api_client.get(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
    )
    assert grant.status_code == 201
    assert permissions.status_code == 200
    assert permissions.json()["active_total"] == 1


def test_last_login_tracks_success_but_not_failed_login(
    api_client: TestClient,
    db_session: Session,
) -> None:
    email, user = _create_account(db_session)
    assert user.last_login_at is None

    assert login(
        api_client, email=email, password="wrong-password-123"
    ).status_code == 401
    db_session.expire_all()
    assert db_session.get(User, user.id).last_login_at is None

    assert login(api_client, email=email).status_code == 200
    db_session.expire_all()
    assert db_session.get(User, user.id).last_login_at is not None


def test_role_changes_preserve_at_least_one_active_administrator(
    api_client: TestClient,
    db_session: Session,
) -> None:
    admin_email, admin = _create_account(
        db_session,
        role=UserRole.ADMINISTRATOR,
    )
    admin_token = _token_for(api_client, admin_email)

    assert api_client.patch(
        f"/api/v1/admin/users/{admin.id}/status",
        headers=bearer(admin_token),
        json={"status": "DISABLED"},
    ).status_code == 409
    db_session.expire_all()
    assert db_session.get(User, admin.id).status == UserStatus.ACTIVE.value
