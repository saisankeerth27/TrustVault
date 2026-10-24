from __future__ import annotations

import io
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import (
    audit_integrity_rate_limiter,
    document_write_rate_limiter,
)
from app.core.security import create_access_token
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.models.enums import UserRole, UserStatus
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.auth import create_account
from app.services.storage import StorageOperationError, get_storage_service
from tests.auth_helpers import DEFAULT_PASSWORD, bearer, login, register, unique_email

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

def test_application_tables_have_row_level_security(db_session: Session) -> None:
    protected_tables = {
        "users",
        "refresh_tokens",
        "documents",
        "document_permissions",
        "document_versions",
        "audit_events",
    }
    enabled_tables = set(
        db_session.scalars(
            text(
                """
                SELECT relation.relname
                FROM pg_class AS relation
                JOIN pg_namespace AS schema
                  ON schema.oid = relation.relnamespace
                WHERE schema.nspname = 'public'
                  AND relation.relkind = 'r'
                  AND relation.relrowsecurity
                """
            )
        ).all()
    )
    assert protected_tables <= enabled_tables


class FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[dict[str, object]] = []
        self.deletions: list[str] = []
        self.downloads: list[str] = []
        self.fail_upload: Exception | None = None
        self.fail_download: Exception | None = None

    def upload_bytes(self, *, key: str, data: bytes, content_type: str) -> None:
        if self.fail_upload is not None:
            raise self.fail_upload
        self.uploads.append({"key": key, "data": data, "content_type": content_type})

    def open_download(self, *, key: str):
        if self.fail_download is not None:
            raise self.fail_download
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


def _token_for(api_client: TestClient, email: str) -> str:
    response = login(api_client, email=email)
    assert response.status_code == 200
    return response.json()["access_token"]


def _register_viewer(api_client: TestClient) -> tuple[str, str, str]:
    email = unique_email("security-viewer")
    response = register(api_client, email=email)
    assert response.status_code == 201
    payload = response.json()
    return email, payload["user"]["id"], payload["access_token"]


def _upload(
    api_client: TestClient,
    token: str,
    *,
    filename: str = "security-report.pdf",
    content_type: str = "application/pdf",
    content: bytes = PDF_BYTES,
    data: dict[str, str] | None = None,
):
    return api_client.post(
        "/api/v1/documents/upload",
        headers=bearer(token),
        files={"file": (filename, content, content_type)},
        data=data or {"category": "Security", "description": "Security test document"},
    )


def _upload_ok(api_client: TestClient, token: str, **overrides) -> dict:
    response = _upload(api_client, token, **overrides)
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


def _events(db_session: Session) -> list[AuditEvent]:
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(AuditEvent).order_by(AuditEvent.chain_index.asc())
        ).all()
    )


def _stored_document(db_session: Session, document_id: str) -> Document:
    db_session.expire_all()
    document = db_session.get(Document, UUID(document_id))
    assert document is not None
    return document


@pytest.mark.parametrize(
    ("method", "suffix", "json_body"),
    [
        ("get", "", None),
        ("get", "/download", None),
        ("patch", "", {"name": "Hijacked.pdf"}),
        ("delete", "", None),
    ],
)
def test_threat_4_1_cross_user_document_operations_are_denied(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    method: str,
    suffix: str,
    json_body: dict | None,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Owner only.pdf")

    other_email, _ = _create_role_user(db_session, UserRole.USER)
    other_token = _token_for(api_client, other_email)

    response = api_client.request(
        method,
        f"/api/v1/documents/{document['id']}{suffix}",
        headers=bearer(other_token),
        json=json_body,
    )

    assert response.status_code == 404
    stored = _stored_document(db_session, document["id"])
    assert stored.name == "Owner only.pdf"
    assert stored.deleted_at is None
    assert fake_storage.downloads == []
    assert fake_storage.deletions == []


def test_threat_4_1_4_4_mr10_grant_read_then_revoke_is_immediate_and_audited(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Shared workflow.pdf")

    viewer_email, _, viewer_token = _register_viewer(api_client)

    initial_operations = [
        ("get", ""),
        ("get", "/download"),
        ("patch", ""),
        ("delete", ""),
    ]
    for method, suffix in initial_operations:
        response = api_client.request(
            method,
            f"/api/v1/documents/{document['id']}{suffix}",
            headers=bearer(viewer_token),
            json={"name": "Denied.pdf"} if method == "patch" else None,
        )
        assert response.status_code == 404
    assert fake_storage.downloads == []
    assert fake_storage.deletions == []

    grant = _grant(api_client, owner_token, document["id"], viewer_email, "READ")
    assert grant.status_code == 201

    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
    ).status_code == 200
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(viewer_token),
    ).status_code == 200
    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
        json={"name": "Read only.pdf"},
    ).status_code == 403
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
    ).status_code == 403

    revoke = api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{grant.json()['id']}",
        headers=bearer(owner_token),
    )
    assert revoke.status_code == 204

    for method, suffix in initial_operations:
        response = api_client.request(
            method,
            f"/api/v1/documents/{document['id']}{suffix}",
            headers=bearer(viewer_token),
            json={"name": "Revoked.pdf"} if method == "patch" else None,
        )
        assert response.status_code == 404
    assert _stored_document(db_session, document["id"]).deleted_at is None

    actions = {event.action for event in _events(db_session)}
    assert {
        "PERMISSION_GRANT",
        "PERMISSION_REVOKE",
        "DOCUMENT_ACCESS_DENIED",
        "DOCUMENT_DOWNLOAD_DENIED",
        "DOCUMENT_EDIT_DENIED",
        "DOCUMENT_DELETE_DENIED",
    }.issubset(actions)


def test_threat_4_1_guessed_and_missing_ids_are_indistinguishable(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Secret existence.pdf")
    stored = _stored_document(db_session, document["id"])

    other_email, _ = _create_role_user(db_session, UserRole.USER)
    other_token = _token_for(api_client, other_email)

    existing_denial = api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(other_token),
    )
    missing_denial = api_client.get(
        f"/api/v1/documents/{uuid4()}",
        headers=bearer(other_token),
    )

    assert existing_denial.status_code == missing_denial.status_code == 404
    assert existing_denial.json() == missing_denial.json()
    assert document["name"] not in existing_denial.text
    assert stored.storage_key not in existing_denial.text


def test_threat_4_2_download_denial_precedes_storage_access(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Private content.pdf")
    stored = _stored_document(db_session, document["id"])

    other_email, _ = _create_role_user(db_session, UserRole.USER)
    other_token = _token_for(api_client, other_email)
    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)

    other_denial = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(other_token),
    )
    admin_denial = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(admin_token),
    )

    assert other_denial.status_code == 404
    assert admin_denial.status_code == 403
    assert fake_storage.downloads == []
    assert stored.storage_key not in other_denial.text
    assert stored.storage_key not in admin_denial.text


def test_threat_4_3_role_injection_is_rejected_at_registration(
    api_client: TestClient,
    db_session: Session,
) -> None:
    email = unique_email("role-injection")
    response = api_client.post(
        "/api/v1/auth/register",
        json={
            "name": "Role Injection",
            "email": email,
            "password": DEFAULT_PASSWORD,
            "role": "ADMINISTRATOR",
        },
    )

    assert response.status_code == 422
    db_session.expire_all()
    assert db_session.scalar(select(User).where(User.email == email)) is None


def test_threat_4_3_forged_admin_claim_cannot_list_accounts(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _, viewer_id, _ = _register_viewer(api_client)
    db_session.expire_all()
    session_id = db_session.scalar(
        select(RefreshToken.family_id)
        .where(
            RefreshToken.user_id == UUID(viewer_id),
            RefreshToken.revoked_at.is_(None),
        )
        .limit(1)
    )
    assert session_id is not None
    forged_token = create_access_token(
        UUID(viewer_id),
        UserRole.ADMINISTRATOR.value,
        session_id,
    )

    response = api_client.get(
        "/api/v1/admin/users",
        headers=bearer(forged_token),
    )

    assert response.status_code == 403
    assert "items" not in response.json()
    denial = [
        event
        for event in _events(db_session)
        if event.action == "AUDIT_ACCESS_DENIED"
    ][-1]
    assert denial.actor_id == UUID(viewer_id)


def test_threat_4_3_4_8_forged_admin_claim_cannot_read_audit(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _, viewer_id, _ = _register_viewer(api_client)
    db_session.expire_all()
    session_id = db_session.scalar(
        select(RefreshToken.family_id)
        .where(
            RefreshToken.user_id == UUID(viewer_id),
            RefreshToken.revoked_at.is_(None),
        )
        .limit(1)
    )
    assert session_id is not None
    forged_token = create_access_token(
        UUID(viewer_id),
        UserRole.ADMINISTRATOR.value,
        session_id,
    )

    response = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(forged_token),
    )

    assert response.status_code == 403
    assert "items" not in response.json()
    denial = [
        event
        for event in _events(db_session)
        if event.action == "AUDIT_ACCESS_DENIED"
    ][-1]
    assert denial.actor_id == UUID(viewer_id)


def test_threat_4_3_administrator_role_does_not_grant_content_or_sharing(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Admin boundary.pdf")

    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    recipient_email, _, _ = _register_viewer(api_client)

    download = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(admin_token),
    )
    grant = _grant(api_client, admin_token, document["id"], recipient_email, "READ")

    assert download.status_code == 403
    assert grant.status_code == 403
    assert fake_storage.downloads == []
    actions = {event.action for event in _events(db_session)}
    assert "DOCUMENT_DOWNLOAD_DENIED" in actions
    assert "PERMISSION_CHANGE_DENIED" in actions


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_status"),
    [
        ("malware.exe", "application/octet-stream", b"MZ executable", 415),
        ("invoice.pdf", "application/pdf", b"MZ executable", 415),
        ("photo.png", "image/png", b"<html><script>alert(1)</script></html>", 415),
        ("empty.pdf", "application/pdf", b"", 422),
        ("missing-type.pdf", "", PDF_BYTES, 415),
        ("resume.docx", "application/octet-stream", b"PK\x03\x04broken", 415),
    ],
)
def test_threat_4_5_malicious_uploads_are_rejected_without_storage(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    filename: str,
    content_type: str,
    content: bytes,
    expected_status: int,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    before = int(db_session.scalar(select(func.count()).select_from(Document)) or 0)

    response = _upload(
        api_client,
        owner_token,
        filename=filename,
        content_type=content_type,
        content=content,
    )

    assert response.status_code == expected_status
    assert fake_storage.uploads == []
    db_session.expire_all()
    after = int(db_session.scalar(select(func.count()).select_from(Document)) or 0)
    assert after == before


def test_threat_4_5_malformed_multipart_is_rejected_without_storage(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    before = int(db_session.scalar(select(func.count()).select_from(Document)) or 0)

    response = api_client.post(
        "/api/v1/documents/upload",
        headers={
            **bearer(owner_token),
            "Content-Type": "multipart/form-data; boundary=broken-boundary",
        },
        content=(
            b"--broken-boundary\r\n"
            b'Content-Disposition: form-data; name="file"; filename="broken.pdf"\r\n'
            b"Content-Type: application/pdf\r\n\r\n"
            + PDF_BYTES
        ),
    )

    assert response.status_code in {400, 422}
    assert fake_storage.uploads == []
    db_session.expire_all()
    after = int(db_session.scalar(select(func.count()).select_from(Document)) or 0)
    assert after == before


@pytest.mark.parametrize(
    "filename",
    [
        "../escape.pdf",
        r"..\escape.pdf",
        "/absolute.pdf",
        "a" * 252 + ".pdf",
    ],
)
def test_threat_4_6_path_manipulation_filenames_are_rejected(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    filename: str,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)

    response = _upload(api_client, owner_token, filename=filename)

    assert response.status_code == 400
    assert fake_storage.uploads == []


@pytest.mark.parametrize("filename", ["bad\x00name.pdf", "bad\x1fname.pdf"])
def test_threat_4_6_control_characters_cannot_reach_storage_keys(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    filename: str,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)

    response = _upload(api_client, owner_token, filename=filename)

    assert response.status_code in {201, 400}
    if response.status_code == 400:
        assert fake_storage.uploads == []
        return

    key = str(fake_storage.uploads[-1]["key"])
    assert key.startswith("documents/")
    assert "\x00" not in key
    assert "\x1f" not in key
    assert filename not in key
    assert all(ord(character) >= 32 for character in response.json()["name"])


def test_threat_4_6_storage_keys_never_use_client_filenames(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, owner = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)

    document = _upload_ok(
        api_client,
        owner_token,
        filename="Quarterly Report 2026.pdf",
    )

    key = str(fake_storage.uploads[-1]["key"])
    assert key.startswith(f"documents/{owner.id}/")
    assert key.endswith(".pdf")
    assert "Quarterly" not in key
    assert "Report" not in key
    assert document["name"] == "Quarterly Report 2026.pdf"


def test_threat_4_7_recipient_cannot_manage_permissions(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Shared permissions.pdf")
    viewer_email, _, viewer_token = _register_viewer(api_client)
    third_email, _, _ = _register_viewer(api_client)

    grant = _grant(api_client, owner_token, document["id"], viewer_email, "READ")
    assert grant.status_code == 201
    permission_id = grant.json()["id"]

    create_attempt = _grant(
        api_client,
        viewer_token,
        document["id"],
        third_email,
        "READ",
    )
    update_attempt = api_client.patch(
        f"/api/v1/documents/{document['id']}/permissions/{permission_id}",
        headers=bearer(viewer_token),
        json={"permission": "EDIT"},
    )
    revoke_attempt = api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{permission_id}",
        headers=bearer(viewer_token),
    )

    assert create_attempt.status_code == 403
    assert update_attempt.status_code == 403
    assert revoke_attempt.status_code == 403
    listing = api_client.get(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
    )
    assert listing.json()["active_total"] == 1
    assert listing.json()["items"][0]["permission"] == "READ"
    assert listing.json()["items"][0]["status"] == "ACTIVE"
    denial_events = [
        event
        for event in _events(db_session)
        if event.action == "PERMISSION_CHANGE_DENIED"
    ]
    assert len(denial_events) >= 3


@pytest.mark.parametrize("path", ["/api/v1/admin/audit-events", "/api/v1/admin/audit-integrity"])
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_threat_4_8_audit_api_rejects_mutation_methods(
    api_client: TestClient,
    db_session: Session,
    method: str,
    path: str,
) -> None:
    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    before = int(db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0)
    latest_id = db_session.scalar(
        select(AuditEvent.id).order_by(AuditEvent.chain_index.desc()).limit(1)
    )

    response = api_client.request(
        method,
        path,
        headers=bearer(admin_token),
        json={"tampered": True},
    )

    assert response.status_code == 405
    db_session.expire_all()
    after = int(db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0)
    assert after == before
    if latest_id is not None:
        assert db_session.get(AuditEvent, latest_id) is not None


def test_threat_4_8_audit_api_has_no_event_mutation_route(
    api_client: TestClient,
    db_session: Session,
) -> None:
    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    event = _events(db_session)[-1]
    before = int(db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0)

    delete_attempt = api_client.delete(
        f"/api/v1/admin/audit-events/{event.id}",
        headers=bearer(admin_token),
    )
    patch_attempt = api_client.patch(
        f"/api/v1/admin/audit-events/{event.id}",
        headers=bearer(admin_token),
        json={"details": {"tampered": True}},
    )

    assert delete_attempt.status_code == 404
    assert patch_attempt.status_code == 404
    db_session.expire_all()
    after = int(db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0)
    assert after == before
    assert db_session.get(AuditEvent, event.id) is not None


def test_threat_4_9_denials_do_not_disclose_document_metadata(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, owner = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Confidential layoffs.pdf")
    stored = _stored_document(db_session, document["id"])

    other_email, _ = _create_role_user(db_session, UserRole.USER)
    other_token = _token_for(api_client, other_email)

    detail = api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(other_token),
    )
    download = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(other_token),
    )

    for response in (detail, download):
        assert response.status_code == 404
        body = response.text
        assert "Confidential layoffs" not in body
        assert stored.storage_key not in body
        assert owner.email not in body
        assert str(owner.id) not in body
        assert "checksum" not in body


def test_threat_4_10_internal_failures_do_not_expose_credentials(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Secret failure.pdf")

    fake_storage.fail_download = StorageOperationError(
        "SECRET-SUPABASE-KEY and SECRET-DATABASE-URL"
    )
    download = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(owner_token),
    )
    assert download.status_code == 503

    fake_storage.fail_upload = StorageOperationError(
        "SECRET-JWT-SIGNING-KEY and SECRET-SERVICE-ROLE"
    )
    upload = _upload(api_client, owner_token, filename="Secret upload.pdf")
    assert upload.status_code == 503

    for response in (download, upload):
        assert "SECRET-" not in response.text
        assert "SUPABASE" not in response.text.upper()
        assert get_settings().require_jwt_secret() not in response.text


def test_threat_4_11_application_authorization_remains_authoritative_with_rls(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Database visible.pdf")

    db_session.expire_all()
    assert db_session.get(Document, UUID(document["id"])) is not None

    other_email, _ = _create_role_user(db_session, UserRole.USER)
    other_token = _token_for(api_client, other_email)
    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)

    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(other_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
    ).status_code == 200
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(admin_token),
    ).status_code == 403
    assert fake_storage.downloads == []


def test_threat_4_12_expired_access_token_is_rejected(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _, viewer_id, _ = _register_viewer(api_client)
    db_session.expire_all()
    session_id = db_session.scalar(
        select(RefreshToken.family_id)
        .where(
            RefreshToken.user_id == UUID(viewer_id),
            RefreshToken.revoked_at.is_(None),
        )
        .limit(1)
    )
    assert session_id is not None
    expired = create_access_token(
        UUID(viewer_id),
        UserRole.USER.value,
        session_id,
        expires_delta=timedelta(seconds=-1),
    )

    response = api_client.get("/api/v1/documents", headers=bearer(expired))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_threat_4_12_tampered_access_token_is_rejected(
    api_client: TestClient,
    db_session: Session,
) -> None:
    viewer_email, _, _ = _register_viewer(api_client)
    token = _token_for(api_client, viewer_email)
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered = f"{header}.{payload}.{replacement}{signature[1:]}"

    response = api_client.get("/api/v1/documents", headers=bearer(tampered))

    assert response.status_code == 401


def test_threat_4_12_logout_invalidates_previously_stolen_access_token(
    api_client: TestClient,
) -> None:
    email = unique_email("stolen-token")
    registration = register(api_client, email=email)
    assert registration.status_code == 201
    token = registration.json()["access_token"]
    assert api_client.get(
        "/api/v1/documents",
        headers=bearer(token),
    ).status_code == 200

    assert api_client.post("/api/v1/auth/logout").status_code == 204
    denied = api_client.get("/api/v1/documents", headers=bearer(token))

    assert denied.status_code == 401
    assert denied.json()["error"]["message"] == "Session is no longer active."


def test_threat_4_12_disabled_users_cannot_access_documents_or_audit(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, owner = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Disabled owner.pdf")
    admin_email, admin = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)

    owner.status = UserStatus.DISABLED.value
    admin.status = UserStatus.DISABLED.value
    db_session.commit()

    assert api_client.get(
        "/api/v1/documents",
        headers=bearer(owner_token),
    ).status_code == 401
    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(owner_token),
    ).status_code == 401
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(owner_token),
    ).status_code == 401
    assert api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
    ).status_code == 401
    assert fake_storage.downloads == []


def test_threat_4_13_brute_force_is_rate_limited_without_disclosure(
    api_client: TestClient,
) -> None:
    email = unique_email("brute-force")
    assert register(api_client, email=email).status_code == 201

    for _ in range(10):
        response = login(
            api_client,
            email=email,
            password="incorrect-password-123",
        )
        assert response.status_code == 401

    blocked = login(api_client, email=email)

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1
    assert email not in blocked.text
    assert DEFAULT_PASSWORD not in blocked.text


def test_document_upload_and_audit_integrity_are_rate_limited(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_email, _ = _create_role_user(db_session, UserRole.USER)
    user_token = _token_for(api_client, user_email)
    monkeypatch.setattr(
        document_write_rate_limiter,
        "consume",
        lambda *_args, **_kwargs: 17,
    )
    upload = _upload(api_client, user_token)
    assert upload.status_code == 429
    assert upload.headers["retry-after"] == "17"
    assert fake_storage.uploads == []

    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    monkeypatch.setattr(
        audit_integrity_rate_limiter,
        "consume",
        lambda *_args, **_kwargs: 29,
    )
    integrity = api_client.get(
        "/api/v1/admin/audit-integrity",
        headers=bearer(admin_token),
    )
    assert integrity.status_code == 429
    assert integrity.headers["retry-after"] == "29"


def test_threat_4_14_oversized_upload_is_rejected_before_storage(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", "40")
    get_settings.cache_clear()
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    before = int(db_session.scalar(select(func.count()).select_from(Document)) or 0)

    try:
        response = _upload(
            api_client,
            owner_token,
            filename="oversized.pdf",
            content=PDF_BYTES + b"x" * (1024 * 1024 + 1024),
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 413
    assert fake_storage.uploads == []
    db_session.expire_all()
    after = int(db_session.scalar(select(func.count()).select_from(Document)) or 0)
    assert after == before


def test_threat_4_14_oversized_upload_is_rejected_before_authentication(
    api_client: TestClient,
) -> None:
    settings = get_settings()
    oversized = PDF_BYTES + b"x" * (
        settings.max_upload_size_bytes + 1024 * 1024 + 1024
    )

    response = api_client.post(
        "/api/v1/documents/upload",
        files={"file": ("oversized.pdf", oversized, "application/pdf")},
        data={"category": "Security", "description": "Unauthenticated oversize"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_threat_4_14_upload_without_content_length_is_rejected(
    api_client: TestClient,
) -> None:
    response = api_client.post(
        "/api/v1/documents/upload",
        content=iter([PDF_BYTES]),
    )

    assert response.status_code == 411
    assert response.json()["error"]["code"] == "length_required"
