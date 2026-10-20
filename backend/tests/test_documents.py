from __future__ import annotations

import hashlib
import io
import logging
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.api.documents as documents_api
from app.core.config import get_settings
from app.main import app
from app.models.document import Document
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth import create_account
from app.services.documents import DocumentPersistenceError, store_document
from app.services.storage import (
    StorageConfigurationError,
    StorageObjectNotFoundError,
    StorageOperationError,
    get_storage_service,
)
from app.services.upload_validation import ValidatedUpload
from tests.auth_helpers import DEFAULT_PASSWORD, bearer, login, register, unique_email

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
DOCUMENT_FIELDS = {
    "id",
    "owner_id",
    "owner_name",
    "name",
    "category",
    "description",
    "mime_type",
    "file_size",
    "checksum",
    "created_at",
    "updated_at",
}


class FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[dict[str, object]] = []
        self.deletions: list[str] = []
        self.downloads: list[str] = []
        self.download_body = PDF_BYTES
        self.fail_upload: Exception | None = None
        self.fail_delete: Exception | None = None
        self.fail_download: Exception | None = None

    def upload_bytes(self, *, key: str, data: bytes, content_type: str) -> None:
        if self.fail_upload is not None:
            raise self.fail_upload
        self.uploads.append({"key": key, "data": data, "content_type": content_type})

    def open_download(self, *, key: str):
        if self.fail_download is not None:
            raise self.fail_download
        self.downloads.append(key)
        return io.BytesIO(self.download_body)

    def delete_object(self, *, key: str) -> None:
        if self.fail_delete is not None:
            raise self.fail_delete
        self.deletions.append(key)


class FailingSession:
    def __init__(self) -> None:
        self.rolled_back = False
        self.document: Document | None = None

    def add(self, document: Document) -> None:
        self.document = document

    def commit(self) -> None:
        raise RuntimeError("database unavailable: SECRET-DB-DETAIL")

    def rollback(self) -> None:
        self.rolled_back = True


@pytest.fixture
def fake_storage(api_client: TestClient):
    storage = FakeStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        yield storage
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


def _create_role_user(db_session: Session, role: UserRole) -> tuple[str, User]:
    email = unique_email(role.value.lower())
    user = create_account(
        db_session,
        name=f"{role.value.title()} User",
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


def _upload(
    client: TestClient,
    token: str,
    *,
    filename: str = "report.pdf",
    content_type: str = "application/pdf",
    content: bytes = PDF_BYTES,
    data: dict[str, str] | None = None,
):
    return client.post(
        "/api/v1/documents/upload",
        headers=bearer(token),
        files={"file": (filename, content, content_type)},
        data=data or {"category": "Finance", "description": "Quarterly report"},
    )


@pytest.mark.parametrize("role", [UserRole.DOCUMENT_OWNER, UserRole.ADMINISTRATOR])
def test_authorized_roles_upload_with_server_metadata(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    role: UserRole,
) -> None:
    email, user = _create_role_user(db_session, role)
    token = _token_for(api_client, email)

    response = _upload(
        api_client,
        token,
        data={
            "category": " Finance ",
            "description": " Quarterly report ",
            "owner_id": str(uuid4()),
            "storage_key": "documents/attacker/chosen.pdf",
            "checksum": "0" * 64,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert set(payload) == DOCUMENT_FIELDS
    assert "storage_key" not in payload
    assert payload["owner_id"] == str(user.id)
    assert payload["owner_name"] == user.name
    assert payload["name"] == "report.pdf"
    assert payload["category"] == "Finance"
    assert payload["description"] == "Quarterly report"
    assert payload["mime_type"] == "application/pdf"
    assert payload["file_size"] == len(PDF_BYTES)
    assert payload["checksum"] == hashlib.sha256(PDF_BYTES).hexdigest()

    assert len(fake_storage.uploads) == 1
    upload = fake_storage.uploads[0]
    key = str(upload["key"])
    assert key.startswith(f"documents/{user.id}/")
    assert key.endswith(".pdf")
    assert "report" not in key
    assert "attacker" not in key
    assert upload["data"] == PDF_BYTES
    assert upload["content_type"] == "application/pdf"

    db_session.expire_all()
    stored = db_session.get(Document, UUID(payload["id"]))
    assert stored is not None
    assert stored.owner_id == user.id
    assert stored.storage_key == key
    assert stored.checksum == payload["checksum"]
    assert stored.file_size == len(PDF_BYTES)


def test_viewer_cannot_upload(
    api_client: TestClient,
    fake_storage: FakeStorage,
) -> None:
    registration = register(api_client, email=unique_email("viewer"))
    assert registration.status_code == 201
    token = registration.json()["access_token"]

    response = _upload(api_client, token)

    assert response.status_code == 403
    assert fake_storage.uploads == []


def test_anonymous_upload_is_rejected(api_client: TestClient) -> None:
    response = _upload(api_client, "not-a-token")
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_status"),
    [
        ("malware.exe", "application/octet-stream", b"MZ executable", 415),
        ("report.pdf", "application/pdf", b"MZ executable", 415),
        ("notes.txt", "application/pdf", b"plain text", 415),
        ("photo.png", "image/png", b"not a png", 415),
        ("report.docx", "application/octet-stream", b"PK\x03\x04broken", 415),
        ("report", "application/pdf", PDF_BYTES, 415),
        ("report.pdf", "application/pdf", b"", 422),
        ("../report.pdf", "application/pdf", PDF_BYTES, 400),
        (r"report\evil.pdf", "application/pdf", PDF_BYTES, 400),
    ],
)
def test_rejects_unsafe_or_mismatched_uploads(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    filename: str,
    content_type: str,
    content: bytes,
    expected_status: int,
) -> None:
    email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, email)

    response = _upload(
        api_client,
        token,
        filename=filename,
        content_type=content_type,
        content=content,
    )

    assert response.status_code == expected_status
    assert fake_storage.uploads == []
    assert "storage_key" not in response.text


def test_oversized_upload_is_rejected(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", "40")
    get_settings.cache_clear()
    email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, email)

    try:
        response = _upload(
            api_client,
            token,
            content=PDF_BYTES + b"x" * 64,
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 413
    assert fake_storage.uploads == []


def test_storage_failure_returns_safe_error_and_no_metadata(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    fake_storage.fail_upload = StorageOperationError(
        "SECRET storage credentials and endpoint detail"
    )
    email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, email)

    response = _upload(api_client, token)

    assert response.status_code == 503
    assert response.json()["error"]["message"] == (
        "Document storage is temporarily unavailable."
    )
    assert "SECRET" not in response.text
    db_session.expire_all()
    assert db_session.scalar(select(Document.id).limit(1)) is None


def test_persistence_failure_returns_generic_error(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, email)

    def fail_persistence(*args, **kwargs):
        raise DocumentPersistenceError("SECRET database detail")

    monkeypatch.setattr(documents_api, "store_document", fail_persistence)
    response = _upload(api_client, token)

    assert response.status_code == 500
    assert response.json()["error"]["message"] == "The upload could not be completed."
    assert "SECRET" not in response.text


def test_database_failure_attempts_object_cleanup_safely(caplog) -> None:
    storage = FakeStorage()
    upload = ValidatedUpload(
        name="report.pdf",
        extension="pdf",
        mime_type="application/pdf",
        size=len(PDF_BYTES),
        checksum=hashlib.sha256(PDF_BYTES).hexdigest(),
        content=PDF_BYTES,
    )
    session = FailingSession()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(DocumentPersistenceError):
            store_document(
                session,
                owner=SimpleNamespace(id=uuid4()),
                upload=upload,
                category="Finance",
                description=None,
                storage=storage,
            )

    assert session.rolled_back
    assert len(storage.uploads) == 1
    assert storage.deletions == [storage.uploads[0]["key"]]
    assert "SECRET" not in caplog.text


def test_cleanup_failure_does_not_leak_storage_details(caplog) -> None:
    storage = FakeStorage()
    storage.fail_delete = StorageOperationError("SECRET cleanup credential")
    upload = ValidatedUpload(
        name="report.pdf",
        extension="pdf",
        mime_type="application/pdf",
        size=len(PDF_BYTES),
        checksum=hashlib.sha256(PDF_BYTES).hexdigest(),
        content=PDF_BYTES,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(DocumentPersistenceError):
            store_document(
                FailingSession(),
                owner=SimpleNamespace(id=uuid4()),
                upload=upload,
                category=None,
                description=None,
                storage=storage,
            )

    assert "Uploaded object cleanup failed" in caplog.text
    assert "SECRET" not in caplog.text


def _upload_ok(
    api_client: TestClient,
    token: str,
    *,
    filename: str,
    category: str = "Finance",
    description: str = "Managed document",
) -> dict:
    response = _upload(
        api_client,
        token,
        filename=filename,
        data={"category": category, "description": description},
    )
    assert response.status_code == 201
    return response.json()


def _stored_document(db_session: Session, document_id: str) -> Document:
    db_session.expire_all()
    document = db_session.get(Document, UUID(document_id))
    assert document is not None
    return document


def test_document_listing_requires_authentication(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/documents")
    assert response.status_code == 401


def test_document_listing_scopes_search_filters_and_pagination(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, owner = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    _upload_ok(api_client, owner_token, filename="Alpha report.pdf")
    _upload_ok(
        api_client,
        owner_token,
        filename="Beta report.pdf",
        category="Legal",
    )
    percent_document = _upload_ok(
        api_client,
        owner_token,
        filename="100% audit.pdf",
        category="Audit",
    )

    other_email, other = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    other_token = _token_for(api_client, other_email)
    _upload_ok(api_client, other_token, filename="Alpha other.pdf")

    owner_list = api_client.get(
        "/api/v1/documents",
        headers=bearer(owner_token),
        params={"sort_by": "name", "order": "asc", "page_size": 1},
    )
    assert owner_list.status_code == 200
    owner_page = owner_list.json()
    assert owner_page["total"] == 3
    assert owner_page["page"] == 1
    assert owner_page["page_size"] == 1
    assert owner_page["pages"] == 3
    assert owner_page["has_next"] is True
    assert owner_page["has_previous"] is False
    assert owner_page["items"][0]["name"] == "100% audit.pdf"
    assert owner_page["items"][0]["owner_name"] == owner.name
    assert set(owner_page["items"][0]) == DOCUMENT_FIELDS

    second_page = api_client.get(
        "/api/v1/documents",
        headers=bearer(owner_token),
        params={"sort_by": "name", "order": "asc", "page_size": 1, "page": 2},
    )
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["name"] == "Alpha report.pdf"
    assert second_page.json()["has_previous"] is True

    searched = api_client.get(
        "/api/v1/documents",
        headers=bearer(owner_token),
        params={"q": "alpha"},
    )
    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert searched.json()["items"][0]["name"] == "Alpha report.pdf"

    wildcard_literal = api_client.get(
        "/api/v1/documents",
        headers=bearer(owner_token),
        params={"q": "%"},
    )
    assert wildcard_literal.status_code == 200
    assert [item["id"] for item in wildcard_literal.json()["items"]] == [
        percent_document["id"]
    ]

    category_filtered = api_client.get(
        "/api/v1/documents",
        headers=bearer(owner_token),
        params={"category": "legal"},
    )
    assert category_filtered.status_code == 200
    assert category_filtered.json()["total"] == 1
    assert category_filtered.json()["items"][0]["name"] == "Beta report.pdf"

    other_owner_scoped = api_client.get(
        "/api/v1/documents",
        headers=bearer(owner_token),
        params={"owner_id": str(other.id)},
    )
    assert other_owner_scoped.status_code == 200
    assert other_owner_scoped.json()["total"] == 0

    other_list = api_client.get(
        "/api/v1/documents",
        headers=bearer(other_token),
    )
    assert other_list.status_code == 200
    assert other_list.json()["total"] == 1
    assert other_list.json()["items"][0]["owner_id"] == str(other.id)

    viewer_registration = register(api_client, email=unique_email("viewer"))
    viewer_token = viewer_registration.json()["access_token"]
    viewer_list = api_client.get(
        "/api/v1/documents",
        headers=bearer(viewer_token),
    )
    assert viewer_list.status_code == 200
    assert viewer_list.json()["total"] == 0

    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    admin_list = api_client.get(
        "/api/v1/documents",
        headers=bearer(admin_token),
    )
    assert admin_list.status_code == 200
    assert admin_list.json()["total"] == 4


def test_invalid_listing_parameters_are_rejected(
    api_client: TestClient,
    db_session: Session,
) -> None:
    email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, email)

    assert api_client.get(
        "/api/v1/documents",
        headers=bearer(token),
        params={"page": 0},
    ).status_code == 422
    assert api_client.get(
        "/api/v1/documents",
        headers=bearer(token),
        params={"page": 100_001},
    ).status_code == 422
    assert api_client.get(
        "/api/v1/documents",
        headers=bearer(token),
        params={"page_size": 101},
    ).status_code == 422
    assert api_client.get(
        "/api/v1/documents",
        headers=bearer(token),
        params={"sort_by": "storage_key"},
    ).status_code == 422
    assert api_client.get(
        "/api/v1/documents",
        headers=bearer(token),
        params={"created_from": "2026-02-02", "created_to": "2026-02-01"},
    ).status_code == 422


def test_document_metadata_visibility_and_management_boundaries(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Private report.pdf")

    other_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    other_token = _token_for(api_client, other_email)
    admin_email, _ = _create_role_user(db_session, UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    viewer_registration = register(api_client, email=unique_email("viewer"))
    viewer_token = viewer_registration.json()["access_token"]

    owner_detail = api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(owner_token),
    )
    assert owner_detail.status_code == 200
    assert owner_detail.json() == document

    admin_detail = api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
    )
    assert admin_detail.status_code == 200
    assert admin_detail.json()["owner_id"] == document["owner_id"]

    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(other_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
    ).status_code == 404

    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
        json={"name": "Admin rename.pdf"},
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(admin_token),
    ).status_code == 404
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(admin_token),
    ).status_code == 404
    assert fake_storage.downloads == []
    assert fake_storage.deletions == []


def test_owner_can_update_only_mutable_metadata(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, token, filename="Original report.pdf")

    updated = api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(token),
        json={
            "name": "  Updated report.pdf  ",
            "category": "  Legal  ",
            "description": "  Updated description  ",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated report.pdf"
    assert updated.json()["category"] == "Legal"
    assert updated.json()["description"] == "Updated description"
    assert set(updated.json()) == DOCUMENT_FIELDS

    stored = _stored_document(db_session, document["id"])
    assert stored.name == "Updated report.pdf"
    assert stored.category == "Legal"
    assert stored.description == "Updated description"

    for payload in (
        {"storage_key": "documents/attacker.pdf"},
        {"owner_id": str(uuid4())},
        {"checksum": "0" * 64},
        {"mime_type": "text/plain"},
        {},
        {"name": "   "},
        {"name": None},
        {"name": "bad\nname.pdf"},
        {"category": "bad\x00category"},
        {"description": "bad\x00description"},
    ):
        response = api_client.patch(
            f"/api/v1/documents/{document['id']}",
            headers=bearer(token),
            json=payload,
        )
        assert response.status_code == 422, payload

    cleared = api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(token),
        json={"category": None, "description": "   "},
    )
    assert cleared.status_code == 200
    assert cleared.json()["category"] is None
    assert cleared.json()["description"] is None


def test_other_owner_and_viewer_cannot_update_document(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Immutable.pdf")

    other_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    other_token = _token_for(api_client, other_email)
    viewer_registration = register(api_client, email=unique_email("viewer"))
    viewer_token = viewer_registration.json()["access_token"]

    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(other_token),
        json={"name": "Steal.pdf"},
    ).status_code == 404
    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
        json={"name": "Viewer edit.pdf"},
    ).status_code == 403


def test_owner_download_streams_safe_private_headers(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, owner_email)
    document = _upload_ok(
        api_client,
        token,
        filename="résumé.pdf",
    )
    stored = _stored_document(db_session, document["id"])

    response = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-length"] == str(len(PDF_BYTES))
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert 'filename="resume.pdf"' in disposition
    assert "filename*=UTF-8''r%C3%A9sum%C3%A9.pdf" in disposition
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert stored.storage_key not in response.text
    assert fake_storage.downloads == [stored.storage_key]


def test_download_disposition_rejects_header_injection(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, owner = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, owner_email)
    document = Document(
        owner_id=owner.id,
        name='report"\r\nX-Injected: yes.pdf',
        category=None,
        description=None,
        storage_key=f"documents/{owner.id}/{uuid4().hex}.pdf",
        mime_type="application/pdf",
        file_size=len(PDF_BYTES),
        checksum=hashlib.sha256(PDF_BYTES).hexdigest(),
    )
    db_session.add(document)
    db_session.commit()

    response = api_client.get(
        f"/api/v1/documents/{document.id}/download",
        headers=bearer(token),
    )

    assert response.status_code == 200
    assert "x-injected" not in response.headers
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert "filename*=UTF-8''report%22%0D%0AX-Injected%3A%20yes.pdf" in disposition


def test_download_is_owner_only(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Private.pdf")

    other_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    other_token = _token_for(api_client, other_email)
    viewer_registration = register(api_client, email=unique_email("viewer"))
    viewer_token = viewer_registration.json()["access_token"]

    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(other_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(viewer_token),
    ).status_code == 403
    assert fake_storage.downloads == []


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_message"),
    [
        (
            StorageObjectNotFoundError("SECRET object detail"),
            404,
            "Document content is unavailable.",
        ),
        (
            StorageConfigurationError("SECRET configuration detail"),
            503,
            "Document storage is not configured.",
        ),
        (
            StorageOperationError("SECRET operation detail"),
            503,
            "Document storage is temporarily unavailable.",
        ),
    ],
)
def test_download_storage_failures_are_safe(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    failure: Exception,
    expected_status: int,
    expected_message: str,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, token, filename="Failure.pdf")
    fake_storage.fail_download = failure

    response = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(token),
    )

    assert response.status_code == expected_status
    assert expected_message in response.text
    assert "SECRET" not in response.text
    assert fake_storage.downloads == []


def test_owner_soft_deletes_document_and_removes_stored_object(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, token, filename="Disposable.pdf")
    stored = _stored_document(db_session, document["id"])
    storage_key = stored.storage_key

    response = api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(token),
    )

    assert response.status_code == 204
    stored = _stored_document(db_session, document["id"])
    assert stored.deleted_at is not None
    assert stored.storage_key == storage_key
    assert fake_storage.deletions == [storage_key]

    assert api_client.get(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(token),
    ).status_code == 404
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(token),
    ).status_code == 404
    assert api_client.get(
        "/api/v1/documents",
        headers=bearer(token),
    ).json()["total"] == 0


def test_delete_is_owner_only_and_cleanup_failure_is_nonfatal(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    caplog,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    owner_token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, owner_token, filename="Delete me.pdf")

    other_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    other_token = _token_for(api_client, other_email)
    viewer_registration = register(api_client, email=unique_email("viewer"))
    viewer_token = viewer_registration.json()["access_token"]

    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(other_token),
    ).status_code == 404
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(viewer_token),
    ).status_code == 403
    assert fake_storage.deletions == []

    fake_storage.fail_delete = StorageOperationError("SECRET cleanup detail")
    with caplog.at_level(logging.ERROR):
        response = api_client.delete(
            f"/api/v1/documents/{document['id']}",
            headers=bearer(owner_token),
        )

    assert response.status_code == 204
    assert _stored_document(db_session, document["id"]).deleted_at is not None
    assert "cleanup failed" in caplog.text
    assert "SECRET" not in caplog.text


def test_delete_storage_configuration_failure_is_nonfatal(
    api_client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    caplog,
) -> None:
    owner_email, _ = _create_role_user(db_session, UserRole.DOCUMENT_OWNER)
    token = _token_for(api_client, owner_email)
    document = _upload_ok(api_client, token, filename="Config cleanup.pdf")
    fake_storage.fail_delete = StorageConfigurationError("SECRET configuration detail")

    with caplog.at_level(logging.ERROR):
        response = api_client.delete(
            f"/api/v1/documents/{document['id']}",
            headers=bearer(token),
        )

    assert response.status_code == 204
    assert _stored_document(db_session, document["id"]).deleted_at is not None
    assert "cleanup failed" in caplog.text
    assert "SECRET" not in caplog.text
