from __future__ import annotations

import hashlib
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
    StorageOperationError,
    get_storage_service,
)
from app.services.upload_validation import ValidatedUpload
from tests.auth_helpers import DEFAULT_PASSWORD, bearer, login, register, unique_email

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
DOCUMENT_FIELDS = {
    "id",
    "owner_id",
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
        self.fail_upload: Exception | None = None
        self.fail_delete: Exception | None = None

    def upload_bytes(self, *, key: str, data: bytes, content_type: str) -> None:
        if self.fail_upload is not None:
            raise self.fail_upload
        self.uploads.append({"key": key, "data": data, "content_type": content_type})

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
