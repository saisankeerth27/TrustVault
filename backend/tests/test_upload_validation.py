from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from app.services import upload_validation
from app.services.upload_validation import (
    MIME_BY_EXTENSION,
    UploadValidationError,
    normalize_optional_text,
    validate_upload,
)

ALLOWED = {"pdf", "txt", "docx", "png", "jpg", "jpeg"}
PDF = b"%PDF-1.7\n%%EOF\n"
TXT = b"TrustVault notes\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"data"
JPEG = b"\xff\xd8\xff\xe0" + b"data"


def docx_bytes(*, include_document: bool = True) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        if include_document:
            archive.writestr("word/document.xml", "<w:document />")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("doc.pdf", "application/pdf", PDF),
        ("notes.txt", "text/plain; charset=utf-8", TXT),
        ("letter.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx_bytes()),
        ("image.png", "image/png", PNG),
        ("image.jpg", "image/jpeg", JPEG),
        ("image.jpeg", "image/jpeg", JPEG),
    ],
)
def test_accepts_supported_files_and_computes_checksum(
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    upload = validate_upload(
        filename=filename,
        declared_content_type=content_type,
        data=content,
        allowed_extensions=ALLOWED,
        max_size_bytes=1024 * 1024,
    )

    extension = filename.rsplit(".", 1)[1]
    assert upload.name == filename
    assert upload.extension == extension
    assert upload.mime_type == MIME_BY_EXTENSION[extension]
    assert upload.size == len(content)
    assert upload.checksum == hashlib.sha256(content).hexdigest()
    assert upload.content == content


def test_rejects_invalid_docx_package() -> None:
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(
            filename="letter.docx",
            declared_content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            data=docx_bytes(include_document=False),
            allowed_extensions=ALLOWED,
            max_size_bytes=1024 * 1024,
        )

    assert exc_info.value.status_code == 415


def test_rejects_docx_with_too_many_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upload_validation, "MAX_DOCX_MEMBERS", 1)

    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(
            filename="letter.docx",
            declared_content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            data=docx_bytes(),
            allowed_extensions=ALLOWED,
            max_size_bytes=1024 * 1024,
        )

    assert exc_info.value.status_code == 415


def test_rejects_docx_that_expands_beyond_uncompressed_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upload_validation, "MAX_DOCX_UNCOMPRESSED_BYTES", 10)

    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(
            filename="letter.docx",
            declared_content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            data=docx_bytes(),
            allowed_extensions=ALLOWED,
            max_size_bytes=1024 * 1024,
        )

    assert exc_info.value.status_code == 415


def test_rejects_extension_removed_from_configuration() -> None:
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(
            filename="doc.pdf",
            declared_content_type="application/pdf",
            data=PDF,
            allowed_extensions={"txt"},
            max_size_bytes=1024 * 1024,
        )

    assert exc_info.value.status_code == 415


def test_unsupported_allowed_extension_fails_closed() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="program.exe",
            declared_content_type="application/octet-stream",
            data=b"MZ",
            allowed_extensions={"exe"},
            max_size_bytes=1024 * 1024,
        )


@pytest.mark.parametrize(
    "filename",
    [
        "",
        ".",
        "..",
        "../doc.pdf",
        r"..\doc.pdf",
        "a\x00.pdf",
        "a" * 252 + ".pdf",
        "bad\x1f.pdf",
        "report\u202egnp.pdf",
    ],
)
def test_rejects_unsafe_filenames(filename: str) -> None:
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(
            filename=filename,
            declared_content_type="application/pdf",
            data=PDF,
            allowed_extensions=ALLOWED,
            max_size_bytes=1024 * 1024,
        )

    assert exc_info.value.status_code == 400


def test_rejects_text_with_binary_content() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload(
            filename="notes.txt",
            declared_content_type="text/plain",
            data=b"hello\x00world",
            allowed_extensions=ALLOWED,
            max_size_bytes=1024 * 1024,
        )


def test_optional_metadata_is_trimmed_and_blank_becomes_none() -> None:
    assert normalize_optional_text("  Finance  ", field="Category", max_length=100) == "Finance"
    assert normalize_optional_text("   ", field="Category", max_length=100) is None
    assert normalize_optional_text(None, field="Category", max_length=100) is None


def test_optional_metadata_rejects_invalid_values() -> None:
    with pytest.raises(UploadValidationError):
        normalize_optional_text("x" * 101, field="Category", max_length=100)
    with pytest.raises(UploadValidationError):
        normalize_optional_text("bad\x00value", field="Description", max_length=2000)
