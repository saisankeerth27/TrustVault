from __future__ import annotations

import io
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.document_permission import DocumentPermission
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.services.auth import create_account
from app.services.storage import get_storage_service
from tests.auth_helpers import DEFAULT_PASSWORD, bearer, login, register, unique_email
from tests.factories import make_user

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

PERMISSION_FIELDS = {
    "id",
    "document_id",
    "user_id",
    "recipient_name",
    "recipient_email",
    "permission",
    "granted_at",
    "revoked_at",
    "status",
}


class FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[dict[str, object]] = []
        self.deletions: list[str] = []
        self.downloads: list[str] = []

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


def _create_role_user(
    db_session: Session,
    role: UserRole,
    *,
    name: str | None = None,
) -> tuple[str, User]:
    email = unique_email(role.value.lower())
    user = create_account(
        db_session,
        name=name or f"{role.value.title()} User",
        email=email,
        password=DEFAULT_PASSWORD,
        role=role,
    )
    db_session.commit()
    return email, user


def _register_viewer(
    api_client: TestClient,
    *,
    name: str = "Shared Viewer",
) -> tuple[str, User, str]:
    email = unique_email("viewer")
    response = register(api_client, email=email, name=name)
    assert response.status_code == 201
    payload = response.json()
    user = api_client.get(
        "/api/v1/auth/me",
        headers=bearer(payload["access_token"]),
    ).json()
    return email, user, payload["access_token"]


def _token_for(api_client: TestClient, email: str) -> str:
    response = login(api_client, email=email)
    assert response.status_code == 200
    return response.json()["access_token"]


def _upload_ok(
    api_client: TestClient,
    token: str,
    *,
    filename: str = "Shared report.pdf",
    category: str = "Finance",
) -> dict:
    response = api_client.post(
        "/api/v1/documents/upload",
        headers=bearer(token),
        files={"file": (filename, PDF_BYTES, "application/pdf")},
        data={"category": category, "description": "Permission test document"},
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


def _permissions(api_client: TestClient, token: str, document_id: str):
    return api_client.get(
        f"/api/v1/documents/{document_id}/permissions",
        headers=bearer(token),
    )


def _permission_rows(db_session: Session, document_id: str) -> list[DocumentPermission]:
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(DocumentPermission)
            .where(DocumentPermission.document_id == UUID(document_id))
            .order_by(DocumentPermission.created_at.asc(), DocumentPermission.id.asc())
        ).all()
    )


def test_owner_grants_read_and_edit_and_lists_current_and_historical_grants(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, owner = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token)

    viewer_email, viewer, viewer_token = _register_viewer(api_client)
    editor_email, editor, _ = _register_viewer(api_client, name="Editor Viewer")
    disabled_email = unique_email("disabled-recipient")
    db_session.add(
        make_user(
            email=disabled_email,
            role=UserRole.VIEWER.value,
            status=UserStatus.DISABLED.value,
        )
    )
    db_session.commit()

    read_grant = _grant(api_client, owner_token, document["id"], viewer_email, "READ")
    assert read_grant.status_code == 201
    read_payload = read_grant.json()
    assert set(read_payload) == PERMISSION_FIELDS
    assert read_payload["document_id"] == document["id"]
    assert read_payload["user_id"] == viewer["id"]
    assert read_payload["recipient_name"] == viewer["name"]
    assert read_payload["recipient_email"] == viewer_email
    assert read_payload["permission"] == "READ"
    assert read_payload["status"] == "ACTIVE"
    assert read_payload["revoked_at"] is None
    assert "password_hash" not in read_grant.text

    edit_grant = _grant(api_client, owner_token, document["id"], editor_email, "EDIT")
    assert edit_grant.status_code == 201
    assert edit_grant.json()["permission"] == "EDIT"

    duplicate = _grant(api_client, owner_token, document["id"], viewer_email, "READ")
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == read_payload["id"]

    conflict = _grant(api_client, owner_token, document["id"], editor_email, "READ")
    assert conflict.status_code == 409

    assert _grant(
        api_client,
        owner_token,
        document["id"],
        viewer_email,
        "WRITE",
    ).status_code == 422
    forged_grantor = api_client.post(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
        json={
            "email": viewer_email,
            "permission": "READ",
            "granted_by": str(uuid4()),
        },
    )
    assert forged_grantor.status_code == 422
    forged_recipient = api_client.post(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
        json={
            "user_id": viewer["id"],
            "permission": "READ",
        },
    )
    assert forged_recipient.status_code == 422

    assert _grant(
        api_client,
        owner_token,
        document["id"],
        owner_email,
        "READ",
    ).status_code == 409
    assert _grant(
        api_client,
        owner_token,
        document["id"],
        unique_email("missing"),
        "READ",
    ).status_code == 404
    assert _grant(
        api_client,
        owner_token,
        document["id"],
        disabled_email,
        "READ",
    ).status_code == 404

    rows = _permission_rows(db_session, document["id"])
    assert len(rows) == 2
    assert {row.user_id for row in rows} == {UUID(viewer["id"]), UUID(editor["id"])}
    assert all(row.granted_by == owner.id for row in rows)
    assert all(row.revoked_at is None for row in rows)

    listing = _permissions(api_client, owner_token, document["id"])
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "no-store"
    assert listing.json()["total"] == 2
    assert listing.json()["active_total"] == 2
    assert all(set(item) == PERMISSION_FIELDS for item in listing.json()["items"])
    assert {item["permission"] for item in listing.json()["items"]} == {"READ", "EDIT"}
    assert all(item["status"] == "ACTIVE" for item in listing.json()["items"])

    other_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    other_token = _token_for(api_client, other_email)
    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)

    assert _permissions(api_client, other_token, document["id"]).status_code == 404
    assert _permissions(api_client, admin_token, document["id"]).status_code == 403
    assert _permissions(api_client, viewer_token, document["id"]).status_code == 403

    assert _grant(
        api_client,
        viewer_token,
        document["id"],
        editor_email,
        "READ",
    ).status_code == 403
    assert _grant(
        api_client,
        other_token,
        document["id"],
        editor_email,
        "READ",
    ).status_code == 404
    assert _grant(
        api_client,
        admin_token,
        document["id"],
        editor_email,
        "READ",
    ).status_code == 403


def test_read_grant_allows_metadata_and_download_but_not_mutation_or_sharing(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    shared_document = _upload_ok(api_client, owner_token, filename="Readable.pdf")
    unrelated_document = _upload_ok(api_client, owner_token, filename="Unrelated.pdf")

    viewer_email, viewer, viewer_token = _register_viewer(api_client)
    grant = _grant(api_client, owner_token, shared_document["id"], viewer_email, "READ")
    assert grant.status_code == 201
    permission_id = grant.json()["id"]

    detail = api_client.get(
        f"/api/v1/documents/{shared_document['id']}",
        headers=bearer(viewer_token),
    )
    assert detail.status_code == 200
    assert detail.json()["access_level"] == "READ"
    assert detail.json()["id"] == shared_document["id"]

    assert api_client.get(
        f"/api/v1/documents/{unrelated_document['id']}",
        headers=bearer(viewer_token),
    ).status_code == 404

    listing = api_client.get("/api/v1/documents", headers=bearer(viewer_token))
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == shared_document["id"]
    assert listing.json()["items"][0]["access_level"] == "READ"

    shared = api_client.get(
        "/api/v1/documents/shared-with-me",
        headers=bearer(viewer_token),
    )
    assert shared.status_code == 200
    assert shared.headers["cache-control"] == "no-store"
    assert shared.json()["total"] == 1
    assert shared.json()["items"][0]["access_level"] == "READ"

    download = api_client.get(
        f"/api/v1/documents/{shared_document['id']}/download",
        headers=bearer(viewer_token),
    )
    assert download.status_code == 200
    assert download.content == PDF_BYTES

    assert api_client.patch(
        f"/api/v1/documents/{shared_document['id']}",
        headers=bearer(viewer_token),
        json={"name": "Read cannot edit.pdf"},
    ).status_code == 403
    assert api_client.delete(
        f"/api/v1/documents/{shared_document['id']}",
        headers=bearer(viewer_token),
    ).status_code == 403
    assert _grant(
        api_client,
        viewer_token,
        shared_document["id"],
        owner_email,
        "EDIT",
    ).status_code == 403
    assert api_client.patch(
        f"/api/v1/documents/{shared_document['id']}/permissions/{permission_id}",
        headers=bearer(viewer_token),
        json={"permission": "EDIT"},
    ).status_code == 403
    assert api_client.delete(
        f"/api/v1/documents/{shared_document['id']}/permissions/{permission_id}",
        headers=bearer(viewer_token),
    ).status_code == 403


def test_edit_grant_allows_metadata_update_but_not_delete_or_sharing(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Editable.pdf")

    editor_email, _, editor_token = _register_viewer(api_client)
    grant = _grant(api_client, owner_token, document["id"], editor_email, "EDIT")
    assert grant.status_code == 201
    permission_id = grant.json()["id"]

    detail = api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(editor_token),
    )
    assert detail.status_code == 200
    assert detail.json()["access_level"] == "EDIT"

    updated = api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(editor_token),
        json={"name": "Edited by recipient.pdf", "category": "Legal"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Edited by recipient.pdf"
    assert updated.json()["access_level"] == "EDIT"

    download = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(editor_token),
    )
    assert download.status_code == 200
    assert download.content == PDF_BYTES

    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(editor_token),
    ).status_code == 403
    assert _permissions(api_client, editor_token, document["id"]).status_code == 403
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{permission_id}",
        headers=bearer(editor_token),
    ).status_code == 403

    owner_delete = api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(owner_token),
    )
    assert owner_delete.status_code == 204


def test_permission_update_preserves_history_and_checks_document_scope(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    first_document = _upload_ok(api_client, owner_token, filename="First.pdf")
    second_document = _upload_ok(api_client, owner_token, filename="Second.pdf")

    viewer_email, _, viewer_token = _register_viewer(api_client)
    grant = _grant(
        api_client,
        owner_token,
        first_document["id"],
        viewer_email,
        "READ",
    )
    assert grant.status_code == 201
    old_id = grant.json()["id"]

    updated = api_client.patch(
        f"/api/v1/documents/{first_document['id']}/permissions/{old_id}",
        headers=bearer(owner_token),
        json={"permission": "EDIT"},
    )
    assert updated.status_code == 200
    updated_payload = updated.json()
    assert updated_payload["permission"] == "EDIT"
    assert updated_payload["status"] == "ACTIVE"
    assert updated_payload["id"] != old_id
    new_id = updated_payload["id"]

    rows = _permission_rows(db_session, first_document["id"])
    assert len(rows) == 2
    old_row = next(row for row in rows if str(row.id) == old_id)
    new_row = next(row for row in rows if str(row.id) == new_id)
    assert old_row.revoked_at is not None
    assert new_row.revoked_at is None
    assert new_row.permission == "EDIT"

    listing = _permissions(api_client, owner_token, first_document["id"])
    assert listing.json()["total"] == 2
    assert listing.json()["active_total"] == 1
    assert {item["status"] for item in listing.json()["items"]} == {"ACTIVE", "REVOKED"}

    same = api_client.patch(
        f"/api/v1/documents/{first_document['id']}/permissions/{new_id}",
        headers=bearer(owner_token),
        json={"permission": "EDIT"},
    )
    assert same.status_code == 200
    assert same.json()["id"] == new_id
    assert len(_permission_rows(db_session, first_document["id"])) == 2

    assert api_client.patch(
        f"/api/v1/documents/{first_document['id']}/permissions/{old_id}",
        headers=bearer(owner_token),
        json={"permission": "READ"},
    ).status_code == 404
    assert api_client.patch(
        f"/api/v1/documents/{second_document['id']}/permissions/{new_id}",
        headers=bearer(owner_token),
        json={"permission": "READ"},
    ).status_code == 404
    assert api_client.patch(
        f"/api/v1/documents/{first_document['id']}/permissions/{new_id}",
        headers=bearer(viewer_token),
        json={"permission": "READ"},
    ).status_code == 403
    assert api_client.patch(
        f"/api/v1/documents/{first_document['id']}/permissions/{new_id}",
        headers=bearer(owner_token),
        json={"permission": "OWNER"},
    ).status_code == 422

    other_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    other_token = _token_for(api_client, other_email)
    assert api_client.patch(
        f"/api/v1/documents/{first_document['id']}/permissions/{new_id}",
        headers=bearer(other_token),
        json={"permission": "READ"},
    ).status_code == 404


def test_revocation_is_immediate_and_regrant_preserves_grant_history(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Revocable.pdf")
    other_document = _upload_ok(api_client, owner_token, filename="Different.pdf")

    viewer_email, _, viewer_token = _register_viewer(api_client)
    grant = _grant(api_client, owner_token, document["id"], viewer_email, "READ")
    assert grant.status_code == 201
    first_id = grant.json()["id"]

    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
    ).status_code == 200

    revoked = api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{first_id}",
        headers=bearer(owner_token),
    )
    assert revoked.status_code == 204

    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(viewer_token),
    ).status_code == 404
    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
        json={"name": "Revoked edit.pdf"},
    ).status_code == 404
    assert api_client.get(
        "/api/v1/documents/shared-with-me",
        headers=bearer(viewer_token),
    ).json()["total"] == 0
    assert api_client.get(
        "/api/v1/documents",
        headers=bearer(viewer_token),
    ).json()["total"] == 0

    repeated = api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{first_id}",
        headers=bearer(owner_token),
    )
    assert repeated.status_code == 204
    assert api_client.delete(
        f"/api/v1/documents/{other_document['id']}/permissions/{first_id}",
        headers=bearer(owner_token),
    ).status_code == 404

    other_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    other_token = _token_for(api_client, other_email)
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{first_id}",
        headers=bearer(other_token),
    ).status_code == 404
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{first_id}",
        headers=bearer(viewer_token),
    ).status_code == 404

    regranted = _grant(api_client, owner_token, document["id"], viewer_email, "READ")
    assert regranted.status_code == 201
    second_id = regranted.json()["id"]
    assert second_id != first_id
    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
    ).status_code == 200

    rows = _permission_rows(db_session, document["id"])
    assert len(rows) == 2
    assert next(row for row in rows if str(row.id) == first_id).revoked_at is not None
    assert next(row for row in rows if str(row.id) == second_id).revoked_at is None
    history = _permissions(api_client, owner_token, document["id"]).json()
    assert history["total"] == 2
    assert history["active_total"] == 1


def test_revoked_edit_grant_loses_future_edit_access(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Edit revoke.pdf")

    editor_email, _, editor_token = _register_viewer(api_client)
    grant = _grant(api_client, owner_token, document["id"], editor_email, "EDIT")
    assert grant.status_code == 201

    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(editor_token),
        json={"name": "Before revoke.pdf"},
    ).status_code == 200

    assert api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{grant.json()['id']}",
        headers=bearer(owner_token),
    ).status_code == 204

    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(editor_token),
        json={"name": "After revoke.pdf"},
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(editor_token),
    ).status_code == 404


def test_administrator_role_does_not_automatically_grant_content_access(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Admin oversight.pdf")

    admin_email, admin = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)

    detail = api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
    )
    assert detail.status_code == 200
    assert detail.json()["access_level"] == "ADMINISTRATOR"
    listed = api_client.get("/api/v1/documents", headers=bearer(admin_token))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["access_level"] == "ADMINISTRATOR"

    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(admin_token),
    ).status_code == 403
    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
        json={"name": "Admin edit.pdf"},
    ).status_code == 403
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
    ).status_code == 403
    assert _permissions(api_client, admin_token, document["id"]).status_code == 403
    assert _grant(
        api_client,
        admin_token,
        document["id"],
        admin_email,
        "EDIT",
    ).status_code == 403

    read_grant = _grant(api_client, owner_token, document["id"], admin_email, "READ")
    assert read_grant.status_code == 201
    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
    ).json()["access_level"] == "READ"
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(admin_token),
    ).status_code == 200
    assert _permissions(api_client, admin_token, document["id"]).status_code == 403

    updated = api_client.patch(
        f"/api/v1/documents/{document['id']}/permissions/{read_grant.json()['id']}",
        headers=bearer(owner_token),
        json={"permission": "EDIT"},
    )
    assert updated.status_code == 200
    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
        json={"name": "Admin with edit grant.pdf"},
    ).status_code == 200
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
    ).status_code == 403

    shared = api_client.get(
        "/api/v1/documents/shared-with-me",
        headers=bearer(admin_token),
    )
    assert shared.status_code == 200
    assert shared.json()["total"] == 1
    assert shared.json()["items"][0]["access_level"] == "EDIT"

    assert api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{updated.json()['id']}",
        headers=bearer(owner_token),
    ).status_code == 204
    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
    ).json()["access_level"] == "ADMINISTRATOR"
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(admin_token),
    ).status_code == 403


def test_shared_with_me_excludes_revoked_and_deleted_documents(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    first_owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    first_owner_token = _token_for(api_client, first_owner_email)
    readable = _upload_ok(api_client, first_owner_token, filename="Readable shared.pdf")
    deleted = _upload_ok(api_client, first_owner_token, filename="Deleted shared.pdf")
    hidden = _upload_ok(api_client, first_owner_token, filename="Not shared.pdf")

    second_owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    second_owner_token = _token_for(api_client, second_owner_email)
    revoked = _upload_ok(api_client, second_owner_token, filename="Revoked shared.pdf")

    recipient_email, _, recipient_token = _register_viewer(api_client)
    assert _grant(
        api_client,
        first_owner_token,
        readable["id"],
        recipient_email,
        "READ",
    ).status_code == 201
    assert _grant(
        api_client,
        first_owner_token,
        deleted["id"],
        recipient_email,
        "EDIT",
    ).status_code == 201
    revoked_grant = _grant(
        api_client,
        second_owner_token,
        revoked["id"],
        recipient_email,
        "READ",
    )
    assert revoked_grant.status_code == 201

    all_shared = api_client.get(
        "/api/v1/documents/shared-with-me",
        headers=bearer(recipient_token),
        params={"page": 1, "page_size": 2, "sort_by": "name", "order": "asc"},
    )
    assert all_shared.status_code == 200
    assert all_shared.json()["total"] == 3
    assert all_shared.json()["pages"] == 2
    assert all_shared.json()["has_next"] is True
    assert len(all_shared.json()["items"]) == 2

    assert api_client.delete(
        f"/api/v1/documents/{revoked['id']}/permissions/{revoked_grant.json()['id']}",
        headers=bearer(second_owner_token),
    ).status_code == 204
    assert api_client.delete(
        f"/api/v1/documents/{deleted['id']}",
        headers=bearer(first_owner_token),
    ).status_code == 204

    active_shared = api_client.get(
        "/api/v1/documents/shared-with-me",
        headers=bearer(recipient_token),
    )
    assert active_shared.status_code == 200
    assert active_shared.json()["total"] == 1
    assert [item["id"] for item in active_shared.json()["items"]] == [readable["id"]]
    assert active_shared.json()["items"][0]["access_level"] == "READ"

    visible_ids = {
        item["id"]
        for item in api_client.get(
            "/api/v1/documents",
            headers=bearer(recipient_token),
        ).json()["items"]
    }
    assert visible_ids == {readable["id"]}
    assert hidden["id"] not in visible_ids
    assert deleted["id"] not in visible_ids
    assert revoked["id"] not in visible_ids

    assert api_client.get(
        f"/api/v1/documents/{deleted['id']}",
        headers=bearer(recipient_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{revoked['id']}",
        headers=bearer(recipient_token),
    ).status_code == 404

    assert api_client.delete(
        f"/api/v1/documents/{readable['id']}/permissions/"
        f"{_permissions(api_client, first_owner_token, readable['id']).json()['items'][0]['id']}",
        headers=bearer(first_owner_token),
    ).status_code == 204
    assert api_client.get(
        "/api/v1/documents/shared-with-me",
        headers=bearer(recipient_token),
    ).json()["total"] == 0


def test_recipient_cannot_access_unrelated_documents_by_id(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    granted = _upload_ok(api_client, owner_token, filename="Granted.pdf")
    unrelated = _upload_ok(api_client, owner_token, filename="Same owner unrelated.pdf")

    viewer_email, _, viewer_token = _register_viewer(api_client)
    assert _grant(
        api_client,
        owner_token,
        granted["id"],
        viewer_email,
        "EDIT",
    ).status_code == 201

    assert api_client.get(
        f"/api/v1/documents/{unrelated['id']}",
        headers=bearer(viewer_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{unrelated['id']}/download",
        headers=bearer(viewer_token),
    ).status_code == 404
    assert api_client.patch(
        f"/api/v1/documents/{unrelated['id']}",
        headers=bearer(viewer_token),
        json={"name": "IDOR attempt.pdf"},
    ).status_code == 404
    assert api_client.delete(
        f"/api/v1/documents/{unrelated['id']}",
        headers=bearer(viewer_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{uuid4()}",
        headers=bearer(viewer_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{uuid4()}/download",
        headers=bearer(viewer_token),
    ).status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("get", "/api/v1/documents", None),
        ("get", "/api/v1/documents/shared-with-me", None),
        ("get", "/api/v1/documents/{document_id}", None),
        ("get", "/api/v1/documents/{document_id}/download", None),
        ("patch", "/api/v1/documents/{document_id}", {"name": "Anonymous.pdf"}),
        ("delete", "/api/v1/documents/{document_id}", None),
        ("get", "/api/v1/documents/{document_id}/permissions", None),
        (
            "post",
            "/api/v1/documents/{document_id}/permissions",
            {"email": "viewer@example.com", "permission": "READ"},
        ),
        (
            "patch",
            "/api/v1/documents/{document_id}/permissions/{permission_id}",
            {"permission": "EDIT"},
        ),
        (
            "delete",
            "/api/v1/documents/{document_id}/permissions/{permission_id}",
            None,
        ),
    ],
)
def test_permission_endpoints_deny_anonymous_requests(
    api_client: TestClient,
    method: str,
    path: str,
    json_body: dict | None,
) -> None:
    document_id = str(uuid4())
    permission_id = str(uuid4())
    formatted_path = path.format(
        document_id=document_id,
        permission_id=permission_id,
    )
    response = api_client.request(
        method,
        formatted_path,
        json=json_body,
    )
    assert response.status_code == 401
