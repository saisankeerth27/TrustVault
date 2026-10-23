from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

import app.api.auth as auth_api
import app.services.documents as documents_service
import app.services.permissions as permissions_service
from app.core.config import get_settings
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.models.enums import UserRole
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.audit import AuditMetadataError, sanitize_details
from app.services.audit_integrity import (
    CheckpointWriteError,
    create_checkpoint,
    verify_audit_trail,
    verify_chain,
)
from app.services.auth import create_account
from app.services.storage import get_storage_service
from tests.auth_helpers import DEFAULT_PASSWORD, bearer, login, register, unique_email

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
CHECKPOINT_KEY = "test-audit-checkpoint-signing-key-0123456789"


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


def _token_for(
    api_client: TestClient,
    email: str,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    response = login(api_client, email=email, headers=headers)
    assert response.status_code == 200
    return response.json()["access_token"]


def _upload(
    api_client: TestClient,
    token: str,
    *,
    filename: str = "audit-report.pdf",
):
    return api_client.post(
        "/api/v1/documents/upload",
        headers=bearer(token),
        files={"file": (filename, PDF_BYTES, "application/pdf")},
        data={"category": "Audit", "description": "Audit test document"},
    )


def _events(db_session: Session) -> list[AuditEvent]:
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(AuditEvent).order_by(AuditEvent.chain_index.asc())
        ).all()
    )


def _event_for(events: list[AuditEvent], action: str) -> AuditEvent:
    matches = [event for event in events if event.action == action]
    assert matches, f"Missing audit action {action}"
    return matches[-1]


def _configure_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    checkpoint_path = tmp_path / "audit-checkpoint.json"
    monkeypatch.setenv("AUDIT_CHECKPOINT_SIGNING_KEY", CHECKPOINT_KEY)
    monkeypatch.setenv("AUDIT_CHECKPOINT_PATH", str(checkpoint_path))
    get_settings.cache_clear()
    return checkpoint_path


def test_auth_audit_events_request_ids_and_no_sensitive_metadata(
    api_client: TestClient,
    db_session: Session,
) -> None:
    email = unique_email("audit-auth")
    registration = register(api_client, email=email)
    assert registration.status_code == 201
    assert registration.headers["x-request-id"]

    request_id = "client-request-123"
    api_client.cookies.clear()
    failed = login(
        api_client,
        email=email,
        password="wrong-password-123",
        headers={"X-Request-ID": request_id},
    )
    assert failed.status_code == 401
    assert failed.headers["x-request-id"] == request_id

    success = login(
        api_client,
        email=email,
        headers={
            "X-Request-ID": "login-success-request",
            "User-Agent": "TrustVault-Audit-Test/1.0",
        },
    )
    assert success.status_code == 200
    assert success.headers["x-request-id"] == "login-success-request"

    logout = api_client.post(
        "/api/v1/auth/logout",
        headers={"X-Request-ID": "logout-request"},
    )
    assert logout.status_code == 204

    events = _events(db_session)
    registration_event = _event_for(events, "USER_REGISTERED")
    failure_event = _event_for(events, "LOGIN_FAILURE")
    login_event = _event_for(events, "LOGIN_SUCCESS")
    logout_event = _event_for(events, "LOGOUT")

    assert registration_event.outcome == "SUCCESS"
    assert failure_event.outcome == "FAILURE"
    assert failure_event.request_id == request_id
    assert failure_event.details["reason"] == "invalid_credentials"
    assert login_event.request_id == "login-success-request"
    assert login_event.details["user_agent"] == "TrustVault-Audit-Test/1.0"
    assert logout_event.request_id == "logout-request"
    assert login_event.actor_id == registration_event.actor_id
    assert logout_event.actor_id == registration_event.actor_id

    serialized = json.dumps([event.details for event in events])
    assert DEFAULT_PASSWORD not in serialized
    assert email.lower() not in serialized
    assert "wrong-password-123" not in serialized

    chain = verify_chain(db_session)
    assert chain.status == "VALID"
    assert [event.chain_index for event in events] == list(
        range(1, len(events) + 1)
    )


def test_document_and_permission_success_events_are_chained(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, owner = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)

    uploaded = _upload(api_client, owner_token)
    assert uploaded.status_code == 201
    document = uploaded.json()

    renamed = api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(owner_token),
        json={"name": "Renamed audit report.pdf"},
    )
    assert renamed.status_code == 200

    downloaded = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(owner_token),
    )
    assert downloaded.status_code == 200
    assert downloaded.content == PDF_BYTES

    viewer_email = unique_email("audit-recipient")
    viewer_registration = register(api_client, email=viewer_email)
    assert viewer_registration.status_code == 201
    viewer_id = viewer_registration.json()["user"]["id"]

    granted = api_client.post(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
        json={"email": viewer_email, "permission": "READ"},
    )
    assert granted.status_code == 201
    grant_id = granted.json()["id"]

    updated = api_client.patch(
        f"/api/v1/documents/{document['id']}/permissions/{grant_id}",
        headers=bearer(owner_token),
        json={"permission": "EDIT"},
    )
    assert updated.status_code == 200
    replacement_id = updated.json()["id"]

    revoked = api_client.delete(
        f"/api/v1/documents/{document['id']}/permissions/{replacement_id}",
        headers=bearer(owner_token),
    )
    assert revoked.status_code == 204

    deleted = api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(owner_token),
    )
    assert deleted.status_code == 204

    events = _events(db_session)
    upload_event = _event_for(events, "DOCUMENT_UPLOAD")
    update_event = _event_for(events, "DOCUMENT_METADATA_UPDATE")
    download_event = _event_for(events, "DOCUMENT_DOWNLOAD")
    grant_event = _event_for(events, "PERMISSION_GRANT")
    permission_update_event = _event_for(events, "PERMISSION_UPDATE")
    revoke_event = _event_for(events, "PERMISSION_REVOKE")
    delete_event = _event_for(events, "DOCUMENT_DELETE")

    assert upload_event.actor_id == owner.id
    assert upload_event.document_id == UUID(document["id"])
    assert upload_event.details["mime_type"] == "application/pdf"
    assert upload_event.details["file_size"] == len(PDF_BYTES)
    assert update_event.details["changed_fields"] == ["name"]
    assert download_event.details["file_size"] == len(PDF_BYTES)
    assert grant_event.details["actor_name"] == owner.name
    assert grant_event.details["recipient_id"] == viewer_id
    assert grant_event.details["permission"] == "READ"
    assert permission_update_event.details["previous_permission"] == "READ"
    assert permission_update_event.details["permission"] == "EDIT"
    assert revoke_event.details["permission"] == "EDIT"
    assert delete_event.outcome == "SUCCESS"

    chain = verify_chain(db_session)
    assert chain.status == "VALID"
    assert chain.event_count == len(events)


def test_denied_actions_are_audited_without_exposing_document_content(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, owner = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    uploaded = _upload(api_client, owner_token)
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]

    viewer_email = unique_email("audit-denied")
    viewer_registration = register(api_client, email=viewer_email)
    viewer_token = viewer_registration.json()["access_token"]
    viewer_id = UUID(viewer_registration.json()["user"]["id"])

    assert (
        api_client.get(
            f"/api/v1/documents/{document_id}",
            headers=bearer(viewer_token),
        ).status_code
        == 404
    )
    assert (
        api_client.patch(
            f"/api/v1/documents/{document_id}",
            headers=bearer(viewer_token),
            json={"name": "Attempted rename"},
        ).status_code
        == 404
    )
    assert (
        api_client.get(
            f"/api/v1/documents/{document_id}/download",
            headers=bearer(viewer_token),
        ).status_code
        == 404
    )
    assert (
        api_client.delete(
            f"/api/v1/documents/{document_id}",
            headers=bearer(viewer_token),
        ).status_code
        == 404
    )
    assert (
        api_client.get(
            f"/api/v1/documents/{document_id}/permissions",
            headers=bearer(viewer_token),
        ).status_code
        == 404
    )
    assert (
        api_client.get(
            "/api/v1/admin/audit-events",
            headers=bearer(viewer_token),
        ).status_code
        == 403
    )

    denied_events = [
        event for event in _events(db_session) if event.outcome == "DENIED"
    ]
    assert {event.action for event in denied_events} == {
        "DOCUMENT_ACCESS_DENIED",
        "DOCUMENT_EDIT_DENIED",
        "DOCUMENT_DOWNLOAD_DENIED",
        "DOCUMENT_DELETE_DENIED",
        "PERMISSION_CHANGE_DENIED",
        "AUDIT_ACCESS_DENIED",
    }
    assert all(event.actor_id == viewer_id for event in denied_events)
    assert all(event.request_id for event in denied_events)

    document_denials = [
        event
        for event in denied_events
        if event.action != "AUDIT_ACCESS_DENIED"
    ]
    assert all(event.document_id == UUID(document_id) for event in document_denials)
    assert all(
        "payload" not in event.details and "content" not in event.details
        for event in denied_events
    )


def test_admin_audit_listing_filters_pagination_and_authorization(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    admin_email, admin = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    owner_email, owner = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token).json()

    listing = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
    )
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "no-store"
    payload = listing.json()
    assert payload["total"] >= 3
    assert payload["items"]
    assert payload["items"][0]["chain_index"] > payload["items"][-1]["chain_index"]

    by_action = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"action": "DOCUMENT_UPLOAD"},
    )
    assert by_action.status_code == 200
    assert by_action.json()["total"] == 1
    assert by_action.json()["items"][0]["document_id"] == document["id"]

    by_actor = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"actor_id": str(owner.id)},
    )
    assert by_actor.status_code == 200
    assert by_actor.json()["total"] >= 2
    assert all(
        item["actor_id"] == str(owner.id) for item in by_actor.json()["items"]
    )

    by_document = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"document_id": document["id"]},
    )
    assert by_document.status_code == 200
    assert by_document.json()["total"] == 1

    target_email, target_user = _create_role_user(db_session, UserRole.USER)
    changed_status = api_client.patch(
        f"/api/v1/admin/users/{target_user.id}/status",
        headers=bearer(admin_token),
        json={"status": "DISABLED"},
    )
    assert changed_status.status_code == 200

    by_target = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"target_user_id": str(target_user.id)},
    )
    assert by_target.status_code == 200
    assert by_target.json()["total"] == 1
    assert by_target.json()["items"][0]["target_user_id"] == str(target_user.id)

    combined = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={
            "actor_id": str(admin.id),
            "target_user_id": str(target_user.id),
            "action": "USER_STATUS_CHANGED",
            "outcome": "SUCCESS",
        },
    )
    assert combined.status_code == 200
    assert combined.json()["total"] == 1

    invalid_id = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"document_id": "not-a-uuid"},
    )
    assert invalid_id.status_code == 422

    by_outcome = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"outcome": "SUCCESS"},
    )
    assert by_outcome.status_code == 200
    assert all(
        item["outcome"] == "SUCCESS" for item in by_outcome.json()["items"]
    )

    today = date.today().isoformat()
    by_date = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"occurred_from": today, "occurred_to": today},
    )
    assert by_date.status_code == 200
    assert by_date.json()["total"] == payload["total"] + 1

    paged = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"page": 1, "page_size": 2},
    )
    assert paged.status_code == 200
    assert len(paged.json()["items"]) == 2
    assert paged.json()["has_next"] is True

    invalid_range = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
        params={"occurred_from": "2026-10-21", "occurred_to": "2026-10-20"},
    )
    assert invalid_range.status_code == 422

    viewer_email = unique_email("audit-api-viewer")
    viewer_token = register(api_client, email=viewer_email).json()["access_token"]
    forbidden = api_client.get(
        "/api/v1/admin/audit-events",
        headers=bearer(viewer_token),
    )
    assert forbidden.status_code == 403
    assert "items" not in forbidden.json()

    anonymous = api_client.get("/api/v1/admin/audit-events")
    assert anonymous.status_code == 401

    invalid_method = api_client.delete(
        "/api/v1/admin/audit-events",
        headers=bearer(admin_token),
    )
    assert invalid_method.status_code == 405

    before_integrity = int(
        db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0
    )
    integrity = api_client.get(
        "/api/v1/admin/audit-integrity",
        headers=bearer(admin_token),
    )
    assert integrity.status_code == 200
    assert integrity.headers["cache-control"] == "no-store"
    assert integrity.json()["chain"]["status"] == "VALID"
    assert integrity.json()["checkpoint"]["status"] == "UNCONFIGURED"
    assert integrity.json()["status"] == "CHAIN_VALID_CHECKPOINT_MISSING"
    assert integrity.json()["verified_at"]
    after_integrity = int(
        db_session.scalar(select(func.count()).select_from(AuditEvent)) or 0
    )
    assert after_integrity == before_integrity
    assert admin.role == "ADMINISTRATOR"


def test_audit_integrity_detects_modified_and_removed_events(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_checkpoint(monkeypatch, tmp_path)
    for index in range(3):
        assert register(api_client, email=unique_email(f"tamper-{index}")).status_code == 201

    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    events = _events(db_session)

    valid = api_client.get(
        "/api/v1/admin/audit-integrity",
        headers=bearer(admin_token),
    )
    assert valid.status_code == 200
    assert valid.json()["chain"]["status"] == "VALID"

    second = events[1]
    db_session.execute(
        update(AuditEvent)
        .where(AuditEvent.id == second.id)
        .values(details={"tampered": True})
    )
    db_session.commit()

    modified = api_client.get(
        "/api/v1/admin/audit-integrity",
        headers=bearer(admin_token),
    )
    assert modified.status_code == 200
    assert modified.json()["status"] == "INVALID"
    assert modified.json()["chain"]["status"] == "INVALID"
    assert modified.json()["chain"]["failure_chain_index"] == second.chain_index

    with pytest.raises(CheckpointWriteError):
        create_checkpoint(db_session, settings=get_settings())


def test_audit_integrity_detects_a_removed_middle_event(
    api_client: TestClient,
    db_session: Session,
) -> None:
    for index in range(3):
        assert register(api_client, email=unique_email(f"remove-{index}")).status_code == 201

    events = _events(db_session)
    db_session.delete(events[1])
    db_session.commit()

    chain = verify_chain(db_session)
    assert chain.status == "INVALID"
    assert chain.failure_chain_index == 3
    assert "missing or reordered" in chain.message


def test_signed_checkpoint_verification_staleness_and_truncation(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkpoint_path = _configure_checkpoint(monkeypatch, tmp_path)
    settings = get_settings()

    assert register(api_client, email=unique_email("checkpoint-one")).status_code == 201
    assert register(api_client, email=unique_email("checkpoint-two")).status_code == 201

    missing = verify_audit_trail(db_session, settings=settings)
    assert missing.status == "CHAIN_VALID_CHECKPOINT_MISSING"
    assert missing.checkpoint.status == "MISSING"

    document = create_checkpoint(db_session, settings=settings)
    assert document["payload"]["event_count"] == 2
    contents = checkpoint_path.read_text(encoding="utf-8")
    assert CHECKPOINT_KEY not in contents
    assert json.loads(contents)["signature"]

    verified = verify_audit_trail(db_session, settings=settings)
    assert verified.status == "VERIFIED"
    assert verified.checkpoint.status == "VALID"

    assert register(api_client, email=unique_email("checkpoint-three")).status_code == 201
    stale = verify_audit_trail(db_session, settings=settings)
    assert stale.status == "CHAIN_VALID_CHECKPOINT_STALE"
    assert stale.checkpoint.status == "STALE"

    create_checkpoint(db_session, settings=settings)
    latest_events = _events(db_session)
    db_session.delete(latest_events[-1])
    db_session.commit()

    truncated = verify_audit_trail(db_session, settings=settings)
    assert truncated.status == "INVALID"
    assert truncated.checkpoint.status == "INVALID"
    assert "shorter" in truncated.checkpoint.message


def test_checkpoint_creation_refuses_to_replace_newer_checkpoint(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_checkpoint(monkeypatch, tmp_path)
    settings = get_settings()

    assert register(api_client, email=unique_email("guard-one")).status_code == 201
    assert register(api_client, email=unique_email("guard-two")).status_code == 201
    create_checkpoint(db_session, settings=settings)

    assert register(api_client, email=unique_email("guard-three")).status_code == 201
    create_checkpoint(db_session, settings=settings)

    latest_events = _events(db_session)
    db_session.delete(latest_events[-1])
    db_session.commit()

    assert verify_audit_trail(db_session, settings=settings).status == "INVALID"
    with pytest.raises(CheckpointWriteError, match="invalid or newer"):
        create_checkpoint(db_session, settings=settings)


def test_signed_checkpoint_rejects_modified_payload(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkpoint_path = _configure_checkpoint(monkeypatch, tmp_path)
    settings = get_settings()
    assert register(api_client, email=unique_email("checkpoint-signature")).status_code == 201

    create_checkpoint(db_session, settings=settings)
    document = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    document["payload"]["last_event_hash"] = "0" * 64
    checkpoint_path.write_text(json.dumps(document), encoding="utf-8")

    result = verify_audit_trail(db_session, settings=settings)
    assert result.status == "INVALID"
    assert result.checkpoint.status == "INVALID"
    assert "signature" in result.checkpoint.message


def test_audit_write_failure_prevents_upload_success(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    before = int(
        db_session.scalar(select(func.count()).select_from(Document)) or 0
    )

    def fail_audit(*args, **kwargs):
        raise documents_service.AuditWriteError("audit unavailable")

    monkeypatch.setattr(documents_service, "record_event", fail_audit)
    response = _upload(api_client, owner_token)

    assert response.status_code == 500
    assert len(fake_storage.uploads) == 1
    assert len(fake_storage.deletions) == 1
    after = int(
        db_session.scalar(select(func.count()).select_from(Document)) or 0
    )
    assert after == before


def test_audit_write_failure_prevents_login_and_permission_success(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = unique_email("audit-login-failure")
    registration = register(api_client, email=email)
    assert registration.status_code == 201
    user = db_session.scalar(select(User).where(User.email == email.lower()))
    assert user is not None
    db_session.expire_all()
    token_count = int(
        db_session.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.user_id == user.id)
        )
        or 0
    )

    def fail_audit(*args, **kwargs):
        raise auth_api.AuditWriteError("audit unavailable")

    monkeypatch.setattr(auth_api, "record_event", fail_audit)
    api_client.cookies.clear()
    login_response = login(api_client, email=email)
    assert login_response.status_code == 500

    db_session.expire_all()
    after_login_count = int(
        db_session.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.user_id == user.id)
        )
        or 0
    )
    assert after_login_count == token_count

    monkeypatch.undo()
    owner_email, _ = _create_role_user(db_session, UserRole.USER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token).json()
    recipient_email = unique_email("permission-audit-failure")
    register(api_client, email=recipient_email)

    def fail_permission_audit(*args, **kwargs):
        raise permissions_service.AuditWriteError("audit unavailable")

    monkeypatch.setattr(permissions_service, "record_event", fail_permission_audit)
    grant = api_client.post(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
        json={"email": recipient_email, "permission": "READ"},
    )
    assert grant.status_code == 500

    db_session.expire_all()
    permissions = api_client.get(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
    )
    assert permissions.status_code == 200
    assert permissions.json()["total"] == 0


def test_unsafe_request_id_is_not_trusted(api_client: TestClient) -> None:
    response = api_client.get(
        "/health",
        headers={"X-Request-ID": "unsafe <script> value"},
    )
    assert response.status_code == 200
    request_id = response.headers["x-request-id"]
    assert request_id != "unsafe <script> value"
    assert len(request_id) == 32
    assert all(character in "0123456789abcdef" for character in request_id)


def test_audit_metadata_rejects_sensitive_or_unsupported_values() -> None:
    with pytest.raises(AuditMetadataError):
        sanitize_details({"password": "secret"})
    with pytest.raises(AuditMetadataError):
        sanitize_details({"session_token": "token"})
    with pytest.raises(AuditMetadataError):
        sanitize_details({"score": 1.5})
    with pytest.raises(AuditMetadataError):
        sanitize_details({"nested": {"bad key": "value"}})

def test_audit_integrity_tampering_detected(
    api_client: TestClient,
    db_session: Session,
) -> None:
    email = unique_email("tamper-audit")
    register(api_client, email=email)
    events = _events(db_session)
    assert len(events) >= 1

    # Verify untampered
    chain = verify_chain(db_session)
    assert chain.status == "VALID"

    # Tamper with the details of the latest event directly in database
    latest = events[-1]
    db_session.execute(
        update(AuditEvent)
        .where(AuditEvent.id == latest.id)
        .values(details={"tampered": "unauthorized-change"})
    )
    db_session.commit()
    db_session.expire_all()

    # Re-verify: must fail with INVALID at latest.chain_index
    tampered_chain = verify_chain(db_session)
    assert tampered_chain.status == "INVALID"
    assert tampered_chain.failure_chain_index == latest.chain_index
    assert f"sequence {latest.chain_index}" in tampered_chain.message


def test_audit_checkpoint_verification_valid_and_tampered_signatures(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkpoint_path = _configure_checkpoint(monkeypatch, tmp_path)
    settings = get_settings()

    # Unconfigured check
    unconfigured_settings = settings.model_copy(update={"audit_checkpoint_signing_key": None})
    trail_unconfigured = verify_audit_trail(db_session, settings=unconfigured_settings)
    assert trail_unconfigured.checkpoint.status == "UNCONFIGURED"

    # Missing check
    trail_missing = verify_audit_trail(db_session, settings=settings)
    assert trail_missing.checkpoint.status == "MISSING"

    # Generate events
    email = unique_email("checkpoint-audit")
    register(api_client, email=email)

    # Create checkpoint
    cp = create_checkpoint(db_session, settings=settings)
    assert cp["payload"]["last_chain_index"] >= 1

    # Verify trail -> VERIFIED
    trail_valid = verify_audit_trail(db_session, settings=settings)
    assert trail_valid.status == "VERIFIED"
    assert trail_valid.checkpoint.status == "VALID"

    # Tamper with checkpoint signature
    with open(checkpoint_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    doc["signature"] = "0" * 64
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(doc, f)

    trail_bad_sig = verify_audit_trail(db_session, settings=settings)
    assert trail_bad_sig.status == "INVALID"
    assert trail_bad_sig.checkpoint.status == "INVALID"
    assert "signature is invalid" in trail_bad_sig.checkpoint.message.lower()
