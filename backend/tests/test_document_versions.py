from __future__ import annotations

import io
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth import create_account
from app.services.storage import (
    StorageConfigurationError,
    StorageObjectNotFoundError,
    StorageOperationError,
    get_storage_service,
)
from tests.auth_helpers import DEFAULT_PASSWORD, bearer, login, register, unique_email

PDF_V1 = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PDF_V2 = b"%PDF-1.4\n2 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
TEXT_V1 = b"Initial notes\n"
TEXT_V2 = "Updated notes with unicode \u2713\n"

VERSION_FIELDS = {
    "id",
    "document_id",
    "version_number",
    "original_filename",
    "mime_type",
    "file_size",
    "checksum",
    "uploaded_by",
    "uploader_name",
    "change_summary",
    "is_current",
    "created_at",
}


class VersionStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploads: list[dict[str, object]] = []
        self.downloads: list[str] = []
        self.deletions: list[str] = []
        self.fail_upload: Exception | None = None
        self.fail_download: Exception | None = None
        self.fail_delete: Exception | None = None

    def upload_bytes(self, *, key: str, data: bytes, content_type: str) -> None:
        if self.fail_upload is not None:
            raise self.fail_upload
        self.objects[key] = data
        self.uploads.append({"key": key, "data": data, "content_type": content_type})

    def open_download(self, *, key: str):
        self.downloads.append(key)
        if self.fail_download is not None:
            raise self.fail_download
        if key not in self.objects:
            raise StorageObjectNotFoundError
        return io.BytesIO(self.objects[key])

    def delete_object(self, *, key: str) -> None:
        if self.fail_delete is not None:
            raise self.fail_delete
        self.deletions.append(key)
        self.objects.pop(key, None)


@pytest.fixture
def version_storage(api_client: TestClient):
    storage = VersionStorage()
    app.dependency_overrides[get_storage_service] = lambda: storage
    try:
        yield storage
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


def _create_user(
    db_session: Session,
    *,
    role: UserRole = UserRole.USER,
    name: str = "Version User",
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


def _upload(
    api_client: TestClient,
    token: str,
    *,
    filename: str = "report.pdf",
    content_type: str = "application/pdf",
    content: bytes = PDF_V1,
) -> dict:
    response = api_client.post(
        "/api/v1/documents/upload",
        headers=bearer(token),
        files={"file": (filename, content, content_type)},
        data={"category": "Contracts", "description": "Versioned document"},
    )
    assert response.status_code == 201
    return response.json()


def _grant(
    api_client: TestClient,
    token: str,
    document_id: str,
    email: str,
    permission: str,
) -> None:
    response = api_client.post(
        f"/api/v1/documents/{document_id}/permissions",
        headers=bearer(token),
        json={"email": email, "permission": permission},
    )
    assert response.status_code == 201


def _versions(api_client: TestClient, token: str, document_id: str):
    return api_client.get(
        f"/api/v1/documents/{document_id}/versions",
        headers=bearer(token),
    )


def _events(db_session: Session) -> list[AuditEvent]:
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(AuditEvent).order_by(AuditEvent.chain_index.asc())
        ).all()
    )


def test_upload_creates_initial_version_and_enforces_history_access(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, owner = _create_user(db_session, name="History Owner")
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    response = _versions(api_client, owner_token, document["id"])

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["total"] == 1
    assert payload["current_version_number"] == 1
    version = payload["items"][0]
    assert set(version) == VERSION_FIELDS
    assert "storage_key" not in version
    assert version["document_id"] == document["id"]
    assert version["version_number"] == 1
    assert version["original_filename"] == "report.pdf"
    assert version["uploader_name"] == owner.name
    assert version["uploaded_by"] == str(owner.id)
    assert version["is_current"] is True
    assert version["change_summary"] == "Initial upload"

    viewer_email, _ = _create_user(db_session, name="History Viewer")
    viewer_token = _token_for(api_client, viewer_email)
    _grant(api_client, owner_token, document["id"], viewer_email, "READ")
    assert _versions(api_client, viewer_token, document["id"]).status_code == 200

    other_email, _ = _create_user(db_session, name="Unrelated User")
    other_token = _token_for(api_client, other_email)
    assert _versions(api_client, other_token, document["id"]).status_code == 404

    admin_email, _ = _create_user(db_session, role=UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    assert _versions(api_client, admin_token, document["id"]).status_code == 403


def test_read_can_preview_and_download_versions_but_not_replace(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)
    viewer_email, _ = _create_user(db_session, name="Read Viewer")
    viewer_token = _token_for(api_client, viewer_email)
    _grant(api_client, owner_token, document["id"], viewer_email, "READ")

    preview = api_client.get(
        f"/api/v1/documents/{document['id']}/preview",
        headers=bearer(viewer_token),
    )
    assert preview.status_code == 200
    assert preview.content == PDF_V1
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.headers["content-disposition"].startswith("inline;")
    assert preview.headers["cache-control"] == "private, no-store"
    assert preview.headers["x-content-type-options"] == "nosniff"

    historical = api_client.get(
        f"/api/v1/documents/{document['id']}/versions/1/download",
        headers=bearer(viewer_token),
    )
    assert historical.status_code == 200
    assert historical.content == PDF_V1
    assert historical.headers["content-disposition"].startswith("attachment;")

    replacement = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(viewer_token),
        files={"file": ("new.pdf", PDF_V2, "application/pdf")},
        data={"expected_version_number": "1"},
    )
    assert replacement.status_code == 403
    text_update = api_client.put(
        f"/api/v1/documents/{document['id']}/content",
        headers=bearer(viewer_token),
        json={"content": "Nope", "expected_version_number": 1},
    )
    assert text_update.status_code == 403
    assert len(version_storage.uploads) == 1

    admin_email, _ = _create_user(db_session, role=UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/preview",
        headers=bearer(admin_token),
    ).status_code == 403


def test_edit_replaces_file_preserves_history_and_rejects_stale_writes(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session, name="Version Owner")
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)
    editor_email, editor = _create_user(db_session, name="Version Editor")
    editor_token = _token_for(api_client, editor_email)
    _grant(api_client, owner_token, document["id"], editor_email, "EDIT")

    replacement = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(editor_token),
        files={"file": ("revised.pdf", PDF_V2, "application/pdf")},
        data={
            "expected_version_number": "1",
            "change_summary": "Updated contract terms",
        },
    )

    assert replacement.status_code == 201
    payload = replacement.json()
    assert payload["document"]["file_size"] == len(PDF_V2)
    assert payload["document"]["checksum"] != document["checksum"]
    assert payload["document"]["access_level"] == "EDIT"
    assert payload["version"]["version_number"] == 2
    assert payload["version"]["is_current"] is True
    assert payload["version"]["uploaded_by"] == str(editor.id)
    assert payload["version"]["change_summary"] == "Updated contract terms"
    assert "storage_key" not in payload["version"]

    db_session.expire_all()
    stored = db_session.get(Document, UUID(document["id"]))
    assert stored is not None
    assert stored.file_size == len(PDF_V2)
    assert len(version_storage.uploads) == 2
    assert version_storage.uploads[-1]["key"] == stored.storage_key

    history = _versions(api_client, owner_token, document["id"]).json()
    assert history["total"] == 2
    assert history["current_version_number"] == 2
    assert [item["version_number"] for item in history["items"]] == [2, 1]
    assert [item["is_current"] for item in history["items"]] == [True, False]

    old_download = api_client.get(
        f"/api/v1/documents/{document['id']}/versions/1/download",
        headers=bearer(owner_token),
    )
    assert old_download.status_code == 200
    assert old_download.content == PDF_V1
    current_download = api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(owner_token),
    )
    assert current_download.status_code == 200
    assert current_download.content == PDF_V2

    stale = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(editor_token),
        files={"file": ("stale.pdf", PDF_V1, "application/pdf")},
        data={"expected_version_number": "1"},
    )
    assert stale.status_code == 409
    assert len(version_storage.uploads) == 2
    assert _versions(api_client, owner_token, document["id"]).json()["total"] == 2

    actions = {event.action for event in _events(db_session)}
    assert {
        "DOCUMENT_VERSION_CREATED",
        "DOCUMENT_VERSION_DOWNLOAD",
    } <= actions
    version_event = next(
        event for event in _events(db_session) if event.action == "DOCUMENT_VERSION_CREATED"
    )
    assert version_event.details["version_number"] == 2
    assert version_event.details["previous_version_number"] == 1
    assert version_event.details["change_summary"] == "Updated contract terms"
    assert version_event.details["source"] == "UPLOAD"


def test_inline_text_editing_creates_version_and_rejects_binary_documents(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    text_document = _upload(
        api_client,
        owner_token,
        filename="notes.txt",
        content_type="text/plain",
        content=TEXT_V1,
    )

    response = api_client.put(
        f"/api/v1/documents/{text_document['id']}/content",
        headers=bearer(owner_token),
        json={"content": TEXT_V2, "expected_version_number": 1},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["version"]["version_number"] == 2
    assert payload["version"]["change_summary"] == "Edited in browser"
    assert payload["version"]["file_size"] == len(TEXT_V2.encode("utf-8"))

    preview = api_client.get(
        f"/api/v1/documents/{text_document['id']}/preview",
        headers=bearer(owner_token),
    )
    assert preview.status_code == 200
    assert preview.content.decode("utf-8") == TEXT_V2

    pdf_document = _upload(api_client, owner_token)
    rejected = api_client.put(
        f"/api/v1/documents/{pdf_document['id']}/content",
        headers=bearer(owner_token),
        json={"content": "Replace with text", "expected_version_number": 1},
    )
    assert rejected.status_code == 415


def test_version_routes_are_authorized_and_handle_storage_failure(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    other_email, _ = _create_user(db_session)
    other_token = _token_for(api_client, other_email)
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/versions/1/download",
        headers=bearer(other_token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/versions/99/download",
        headers=bearer(owner_token),
    ).status_code == 404

    admin_email, _ = _create_user(db_session, role=UserRole.ADMINISTRATOR)
    admin_token = _token_for(api_client, admin_email)
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/versions/1/download",
        headers=bearer(admin_token),
    ).status_code == 403

    version_storage.fail_upload = StorageOperationError("SECRET storage detail")
    failed = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("revised.pdf", PDF_V2, "application/pdf")},
        data={"expected_version_number": "1"},
    )
    assert failed.status_code == 503
    assert "SECRET" not in failed.text
    history = _versions(api_client, owner_token, document["id"]).json()
    assert history["total"] == 1
    assert history["current_version_number"] == 1


def test_soft_delete_removes_current_and_historical_version_objects(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)
    replacement = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("revised.pdf", PDF_V2, "application/pdf")},
        data={"expected_version_number": "1"},
    )
    assert replacement.status_code == 201

    historical_key = str(version_storage.uploads[0]["key"])
    current_key = str(version_storage.uploads[1]["key"])
    assert historical_key != current_key

    deleted = api_client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(owner_token),
    )

    assert deleted.status_code == 204
    assert set(version_storage.deletions) == {historical_key, current_key}


def test_missing_document_version_routes_do_not_touch_storage(
    api_client: TestClient,
    version_storage: VersionStorage,
) -> None:
    registration = register(api_client, email=unique_email("version-anonymous"))
    assert registration.status_code == 201
    token = registration.json()["access_token"]
    missing_document = uuid4()

    assert api_client.get(
        f"/api/v1/documents/{missing_document}/versions",
        headers=bearer(token),
    ).status_code == 404
    assert api_client.get(
        f"/api/v1/documents/{missing_document}/preview",
        headers=bearer(token),
    ).status_code == 404
    assert version_storage.uploads == []


def test_version_creation_rejects_missing_documents_and_invalid_input(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    missing = api_client.put(
        f"/api/v1/documents/{uuid4()}/versions",
        headers=bearer(owner_token),
        files={"file": ("revised.pdf", PDF_V2, "application/pdf")},
        data={"expected_version_number": "1"},
    )
    assert missing.status_code == 404

    invalid_type = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("payload.exe", b"not allowed", "application/octet-stream")},
        data={"expected_version_number": "1"},
    )
    assert invalid_type.status_code == 415

    long_summary = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("revised.pdf", PDF_V2, "application/pdf")},
        data={
            "expected_version_number": "1",
            "change_summary": "x" * 501,
        },
    )
    assert long_summary.status_code == 422
    assert len(version_storage.uploads) == 1


def test_text_editing_rejects_stale_writes_and_storage_failures(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(
        api_client,
        owner_token,
        filename="notes.txt",
        content_type="text/plain",
        content=TEXT_V1,
    )
    first_edit = api_client.put(
        f"/api/v1/documents/{document['id']}/content",
        headers=bearer(owner_token),
        json={"content": TEXT_V2, "expected_version_number": 1},
    )
    assert first_edit.status_code == 201

    stale = api_client.put(
        f"/api/v1/documents/{document['id']}/content",
        headers=bearer(owner_token),
        json={"content": "Stale edit", "expected_version_number": 1},
    )
    assert stale.status_code == 409
    assert "Refresh the version history" in stale.json()["error"]["message"]

    version_storage.fail_upload = StorageConfigurationError(
        "SECRET text storage configuration"
    )
    unavailable = api_client.put(
        f"/api/v1/documents/{document['id']}/content",
        headers=bearer(owner_token),
        json={"content": "New edit", "expected_version_number": 2},
    )
    assert unavailable.status_code == 503
    assert "SECRET" not in unavailable.text
    assert _versions(api_client, owner_token, document["id"]).json()["total"] == 2


def test_text_editing_requires_available_version_history(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(
        api_client,
        owner_token,
        filename="notes.txt",
        content_type="text/plain",
        content=TEXT_V1,
    )
    db_session.execute(
        delete(DocumentVersion).where(
            DocumentVersion.document_id == UUID(document["id"])
        )
    )
    db_session.commit()

    response = api_client.put(
        f"/api/v1/documents/{document['id']}/content",
        headers=bearer(owner_token),
        json={"content": "Edited", "expected_version_number": 1},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == (
        "Document version history is unavailable."
    )
    assert len(version_storage.uploads) == 1


def test_version_persistence_failure_cleans_up_new_object(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("SECRET persistence failure")

    monkeypatch.setattr(
        "app.services.document_versions.record_event",
        fail_audit,
    )
    response = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("revised.pdf", PDF_V2, "application/pdf")},
        data={"expected_version_number": "1"},
    )

    assert response.status_code == 500
    assert response.json()["error"]["message"] == (
        "The new document version could not be saved."
    )
    assert "SECRET" not in response.text
    assert len(version_storage.uploads) == 2
    assert version_storage.deletions == [version_storage.uploads[1]["key"]]
    assert _versions(api_client, owner_token, document["id"]).json()["total"] == 1


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_message"),
    [
        (
            StorageObjectNotFoundError("SECRET missing object"),
            404,
            "Document content is unavailable.",
        ),
        (
            StorageConfigurationError("SECRET configuration"),
            503,
            "Document storage is not configured.",
        ),
        (
            StorageOperationError("SECRET operation"),
            503,
            "Document storage is temporarily unavailable.",
        ),
    ],
)
def test_preview_and_version_download_storage_failures_are_safe(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
    failure: Exception,
    expected_status: int,
    expected_message: str,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)
    version_storage.fail_download = failure

    for path in (
        f"/api/v1/documents/{document['id']}/preview",
        f"/api/v1/documents/{document['id']}/versions/1/download",
    ):
        response = api_client.get(path, headers=bearer(owner_token))
        assert response.status_code == expected_status
        assert response.json()["error"]["message"] == expected_message
        assert "SECRET" not in response.text


def test_preview_and_version_download_audit_failures_are_safe(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("SECRET audit failure")

    monkeypatch.setattr("app.api.documents.record_event", fail_audit)

    preview = api_client.get(
        f"/api/v1/documents/{document['id']}/preview",
        headers=bearer(owner_token),
    )
    assert preview.status_code == 500
    assert preview.json()["error"]["message"] == "The preview could not be completed."
    assert "SECRET" not in preview.text

    download = api_client.get(
        f"/api/v1/documents/{document['id']}/versions/1/download",
        headers=bearer(owner_token),
    )
    assert download.status_code == 500
    assert download.json()["error"]["message"] == (
        "The download could not be completed."
    )
    assert "SECRET" not in download.text

def test_version_history_is_paginated_newest_first_without_duplicates(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    for version_number in range(2, 14):
        response = api_client.put(
            f"/api/v1/documents/{document['id']}/versions",
            headers=bearer(owner_token),
            files={
                "file": (
                    f"v{version_number}.pdf",
                    b"%PDF-1.4\n" + str(version_number).encode(),
                    "application/pdf",
                )
            },
            data={"expected_version_number": str(version_number - 1)},
        )
        assert response.status_code == 201

    first = api_client.get(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
    )
    assert first.status_code == 200
    first_page = first.json()
    assert first_page["total"] == 13
    assert first_page["page"] == 1
    assert first_page["page_size"] == 5
    assert first_page["pages"] == 3
    assert first_page["has_next"] is True
    assert first_page["has_previous"] is False
    assert [item["version_number"] for item in first_page["items"]] == [
        13,
        12,
        11,
        10,
        9,
    ]

    pages = [first_page]
    for page in (2, 3):
        response = api_client.get(
            f"/api/v1/documents/{document['id']}/versions",
            params={"page": page},
            headers=bearer(owner_token),
        )
        assert response.status_code == 200
        pages.append(response.json())

    assert [item["version_number"] for item in pages[1]["items"]] == [
        8,
        7,
        6,
        5,
        4,
    ]
    assert [item["version_number"] for item in pages[2]["items"]] == [3, 2, 1]
    assert pages[2]["has_next"] is False
    assert pages[2]["has_previous"] is True
    all_version_numbers = [
        item["version_number"] for page in pages for item in page["items"]
    ]
    assert len(all_version_numbers) == len(set(all_version_numbers)) == 13

    empty_page = api_client.get(
        f"/api/v1/documents/{document['id']}/versions",
        params={"page": 4},
        headers=bearer(owner_token),
    )
    assert empty_page.status_code == 200
    assert empty_page.json()["items"] == []
    assert empty_page.json()["has_next"] is False
    assert empty_page.json()["has_previous"] is True

    oversized = api_client.get(
        f"/api/v1/documents/{document['id']}/versions",
        params={"page_size": 101},
        headers=bearer(owner_token),
    )
    assert oversized.status_code == 422


def test_owner_can_delete_historical_version(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session, name="Owner User")
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token, filename="contract.pdf")

    # Create version 2
    res2 = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("contract-v2.pdf", b"%PDF-1.4\nrevised-content", "application/pdf")},
        data={"expected_version_number": "1", "change_summary": "Revised terms"},
    )
    assert res2.status_code == 201

    # Check versions list: 2 versions, total_size is sum
    list_res = api_client.get(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
    )
    assert list_res.status_code == 200
    versions = list_res.json()["items"]
    assert len(versions) == 2
    initial_total_size = list_res.json()["total_size"]

    # Delete historical version 1
    del_res = api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/1",
        headers=bearer(owner_token),
    )
    assert del_res.status_code == 200
    del_body = del_res.json()
    assert del_body["deleted_version_number"] == 1
    assert del_body["storage_deleted"] is True
    assert del_body["retained_total_size"] < initial_total_size

    # Verify version 1 is gone from versions list and storage
    list_after = api_client.get(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
    )
    assert list_after.status_code == 200
    after_versions = list_after.json()["items"]
    assert len(after_versions) == 1
    assert after_versions[0]["version_number"] == 2
    assert after_versions[0]["is_current"] is True
    assert list_after.json()["total_size"] == del_body["retained_total_size"]

    # Verify audit event remains
    events = list(
        db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.document_id == UUID(document["id"]))
            .order_by(AuditEvent.chain_index.asc())
        ).all()
    )
    delete_events = [e for e in events if e.action == "DOCUMENT_VERSION_DELETE"]
    assert len(delete_events) == 1
    assert delete_events[0].outcome == "SUCCESS"
    assert delete_events[0].details["version_number"] == 1


def test_current_version_deletion_rolls_back_to_highest_remaining_version(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token, content=PDF_V1)
    version_one = _versions(api_client, owner_token, document["id"]).json()["items"][0]

    last_version = api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/1",
        headers=bearer(owner_token),
    )
    assert last_version.status_code == 400
    assert "at least one document version" in (
        last_version.json()["error"]["message"].lower()
    )
    assert version_one["id"] in {
        version["id"]
        for version in _versions(api_client, owner_token, document["id"]).json()[
            "items"
        ]
    }

    create_v2 = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("v2.pdf", PDF_V2, "application/pdf")},
        data={"expected_version_number": "1"},
    )
    assert create_v2.status_code == 201
    assert create_v2.json()["version"]["version_number"] == 2

    rollback = api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/2",
        headers=bearer(owner_token),
    )
    assert rollback.status_code == 200
    body = rollback.json()
    assert body["deleted_version_number"] == 2
    assert body["rolled_back"] is True
    assert body["current_version"]["version_number"] == 1
    assert body["document"]["checksum"] == version_one["checksum"]
    assert body["document"]["file_size"] == version_one["file_size"]

    after = _versions(api_client, owner_token, document["id"]).json()
    assert after["total"] == 1
    assert after["current_version_number"] == 1
    assert after["items"][0]["id"] == version_one["id"]
    assert after["items"][0]["is_current"] is True

    preview = api_client.get(
        f"/api/v1/documents/{document['id']}/preview",
        headers=bearer(owner_token),
    )
    assert preview.status_code == 200
    assert preview.content == PDF_V1

    create_v3 = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("v3.pdf", PDF_V2, "application/pdf")},
        data={"expected_version_number": "1"},
    )
    assert create_v3.status_code == 201
    assert create_v3.json()["version"]["version_number"] == 3

    db_session.expire_all()
    stored_document = db_session.get(Document, UUID(document["id"]))
    assert stored_document is not None
    assert stored_document.next_version_number == 4

    rollback_event = next(
        event
        for event in _events(db_session)
        if event.action == "DOCUMENT_VERSION_DELETE"
        and event.details.get("version_number") == 2
    )
    assert rollback_event.details["rollback"] is True
    assert rollback_event.details["rolled_back_to_version_number"] == 1
    assert rollback_event.details["current_version_number"] == 1
    assert rollback_event.details["was_current"] is True


def test_edit_and_read_recipients_cannot_delete_historical_version(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session, name="Owner")
    editor_email, _ = _create_user(db_session, name="Editor")
    reader_email, _ = _create_user(db_session, name="Reader")
    owner_token = _token_for(api_client, owner_email)
    editor_token = _token_for(api_client, editor_email)
    reader_token = _token_for(api_client, reader_email)

    document = _upload(api_client, owner_token)
    api_client.post(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
        json={"email": editor_email, "permission": "EDIT"},
    )
    api_client.post(
        f"/api/v1/documents/{document['id']}/permissions",
        headers=bearer(owner_token),
        json={"email": reader_email, "permission": "READ"},
    )

    # Create version 2
    api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("v2.pdf", b"%PDF-1.4\nv2", "application/pdf")},
        data={"expected_version_number": "1"},
    )

    # Editor attempt to delete version 1 -> 403 Forbidden
    del_editor = api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/1",
        headers=bearer(editor_token),
    )
    assert del_editor.status_code == 403
    assert "only the document owner" in del_editor.json()["error"]["message"].lower()

    # Reader attempt to delete version 1 -> 403 Forbidden
    del_reader = api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/1",
        headers=bearer(reader_token),
    )
    assert del_reader.status_code == 403

    # Check denial audit event
    events = list(
        db_session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.document_id == UUID(document["id"]),
                AuditEvent.action == "DOCUMENT_VERSION_DELETE",
            )
        ).all()
    )
    assert any(e.outcome == "DENIED" for e in events)


def test_user_a_cannot_delete_user_b_historical_version(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    user_a_email, _ = _create_user(db_session, name="User A")
    user_b_email, _ = _create_user(db_session, name="User B")
    token_a = _token_for(api_client, user_a_email)
    token_b = _token_for(api_client, user_b_email)

    document_a = _upload(api_client, token_a)
    api_client.put(
        f"/api/v1/documents/{document_a['id']}/versions",
        headers=bearer(token_a),
        files={"file": ("v2.pdf", b"%PDF-1.4\nv2", "application/pdf")},
        data={"expected_version_number": "1"},
    )

    # User B tries to delete version 1 of document A
    res = api_client.delete(
        f"/api/v1/documents/{document_a['id']}/versions/1",
        headers=bearer(token_b),
    )
    assert res.status_code in (403, 404)


def test_delete_historical_version_rejects_invalid_version_safely(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    res = api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/999",
        headers=bearer(owner_token),
    )
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Document version not found."


def test_failed_storage_deletion_does_not_report_success(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, _ = _create_user(db_session)
    owner_token = _token_for(api_client, owner_email)
    document = _upload(api_client, owner_token)

    api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
        files={"file": ("v2.pdf", b"%PDF-1.4\nv2", "application/pdf")},
        data={"expected_version_number": "1"},
    )

    version_storage.fail_delete = StorageOperationError("Storage network failure")
    res = api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/1",
        headers=bearer(owner_token),
    )
    assert res.status_code == 503
    assert "could not be safely deleted" in res.json()["error"]["message"].lower()

    # Verify version 1 was NOT deleted from DB
    list_res = api_client.get(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
    )
    assert len(list_res.json()["items"]) == 2

    current_failure = api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/2",
        headers=bearer(owner_token),
    )
    assert current_failure.status_code == 503
    list_after_current_failure = api_client.get(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(owner_token),
    ).json()
    assert list_after_current_failure["total"] == 2
    assert list_after_current_failure["current_version_number"] == 2

    version_storage.fail_delete = None
    current_rollback = api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/2",
        headers=bearer(owner_token),
    )
    assert current_rollback.status_code == 200
    assert current_rollback.json()["rolled_back"] is True
    assert current_rollback.json()["current_version"]["version_number"] == 1


def test_document_activity_is_filtered_and_paginated_for_owner(
    api_client: TestClient,
    db_session: Session,
    version_storage: VersionStorage,
) -> None:
    owner_email, owner = _create_user(db_session, name="Akash Owner")
    editor_email, editor = _create_user(db_session, name="Akash Editor")
    admin_email, _ = _create_user(
        db_session,
        role=UserRole.ADMINISTRATOR,
        name="Audit Admin",
    )
    owner_token = _token_for(api_client, owner_email)
    editor_token = _token_for(api_client, editor_email)
    admin_token = _token_for(api_client, admin_email)

    document = _upload(
        api_client,
        owner_token,
        filename="notes.txt",
        content_type="text/plain",
        content=b"Initial notes\n",
    )
    _grant(api_client, owner_token, document["id"], editor_email, "EDIT")

    assert api_client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=bearer(editor_token),
        json={"description": "Updated semester notes"},
    ).status_code == 200
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/preview",
        headers=bearer(editor_token),
    ).status_code == 200
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(editor_token),
    ).status_code == 200
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/preview",
        headers=bearer(owner_token),
    ).status_code == 200
    assert api_client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=bearer(owner_token),
    ).status_code == 200
    create_v2 = api_client.put(
        f"/api/v1/documents/{document['id']}/versions",
        headers=bearer(editor_token),
        files={"file": ("v2.txt", b"Revised notes\n", "text/plain")},
        data={"expected_version_number": "1", "change_summary": "Editor revision"},
    )
    assert create_v2.status_code == 201
    assert api_client.delete(
        f"/api/v1/documents/{document['id']}/versions/1",
        headers=bearer(editor_token),
    ).status_code == 403

    first_page = api_client.get(
        f"/api/v1/documents/{document['id']}/activity",
        headers=bearer(owner_token),
    )
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert first_payload["page"] == 1
    assert first_payload["page_size"] == 5
    assert first_payload["total"] == 7
    assert first_payload["pages"] == 2
    assert first_payload["has_next"] is True
    assert first_payload["has_previous"] is False
    assert len(first_payload["items"]) == 5

    second_page = api_client.get(
        f"/api/v1/documents/{document['id']}/activity",
        params={"page": 2},
        headers=bearer(owner_token),
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["page"] == 2
    assert second_payload["has_next"] is False
    assert second_payload["has_previous"] is True
    items = first_payload["items"] + second_payload["items"]
    assert len(items) == len({item["id"] for item in items}) == 7

    owner_routine_actions = {
        "DOCUMENT_PREVIEW",
        "DOCUMENT_DOWNLOAD",
        "DOCUMENT_VERSION_DOWNLOAD",
    }
    assert not any(
        item["actor_id"] == str(owner.id)
        and item["action"] in owner_routine_actions
        for item in items
    )
    actions = {item["action"] for item in items}
    assert {
        "DOCUMENT_UPLOAD",
        "PERMISSION_GRANT",
        "DOCUMENT_METADATA_UPDATE",
        "DOCUMENT_PREVIEW",
        "DOCUMENT_DOWNLOAD",
        "DOCUMENT_VERSION_CREATED",
        "DOCUMENT_VERSION_DELETE",
    } <= actions

    metadata_event = next(
        item for item in items if item["action"] == "DOCUMENT_METADATA_UPDATE"
    )
    assert metadata_event["actor_id"] == str(editor.id)
    assert metadata_event["actor_name"] == "Akash Editor"
    assert "description" in metadata_event["details"]["field_changes"]
    assert (
        metadata_event["details"]["field_changes"]["description"]["new"]
        == "Updated semester notes"
    )

    denied_delete = next(
        item
        for item in items
        if item["action"] == "DOCUMENT_VERSION_DELETE"
    )
    assert denied_delete["outcome"] == "DENIED"

    admin_events = api_client.get(
        "/api/v1/admin/audit-events",
        params={"document_id": document["id"], "page_size": 100},
        headers=bearer(admin_token),
    )
    assert admin_events.status_code == 200
    admin_payload = admin_events.json()
    assert admin_payload["total"] == 9
    admin_actions = [item["action"] for item in admin_payload["items"]]
    assert admin_actions.count("DOCUMENT_PREVIEW") == 2
    assert admin_actions.count("DOCUMENT_DOWNLOAD") == 2
    assert any(
        item["actor_id"] == str(owner.id)
        and item["action"] == "DOCUMENT_PREVIEW"
        for item in admin_payload["items"]
    )

    denied = api_client.get(
        f"/api/v1/documents/{document['id']}/activity",
        headers=bearer(editor_token),
    )
    assert denied.status_code == 403
