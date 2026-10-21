"""Server-side validation for uploaded document bytes and metadata."""

from __future__ import annotations

import hashlib
import io
import unicodedata
import zipfile
from dataclasses import dataclass

MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

MAX_DOCX_MEMBERS = 1000
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024


class UploadValidationError(Exception):
    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ValidatedUpload:
    name: str
    extension: str
    mime_type: str
    size: int
    checksum: str
    content: bytes


def normalize_optional_text(
    value: str | None,
    *,
    field: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if "\x00" in stripped:
        raise UploadValidationError(f"{field} contains invalid characters.")
    if len(stripped) > max_length:
        raise UploadValidationError(f"{field} is too long.")
    return stripped


def _validated_filename(filename: str | None) -> str:
    if not isinstance(filename, str):
        raise UploadValidationError("A filename is required.", status_code=400)

    candidate = filename.strip()
    if not candidate or candidate in {".", ".."}:
        raise UploadValidationError("The filename is invalid.", status_code=400)
    if len(candidate) > 255:
        raise UploadValidationError("The filename is too long.", status_code=400)
    if any(character in candidate for character in ("/", "\\", "\x00")):
        raise UploadValidationError("The filename is invalid.", status_code=400)
    if any(ord(character) < 32 or ord(character) == 127 for character in candidate):
        raise UploadValidationError("The filename is invalid.", status_code=400)
    if any(unicodedata.category(character) == "Cf" for character in candidate):
        raise UploadValidationError("The filename is invalid.", status_code=400)

    return candidate


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _validate_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > MAX_DOCX_MEMBERS:
                return False
            if sum(member.file_size for member in members) > MAX_DOCX_UNCOMPRESSED_BYTES:
                return False
            names = {member.filename for member in members}
            return "[Content_Types].xml" in names and "word/document.xml" in names
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError, RuntimeError):
        return False


def _signature_matches(extension: str, data: bytes) -> bool:
    if extension == "pdf":
        return data.startswith(b"%PDF-")
    if extension == "txt":
        if b"\x00" in data:
            return False
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return False
        return True
    if extension == "docx":
        return data.startswith(b"PK\x03\x04") and _validate_docx(data)
    if extension == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {"jpg", "jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    return False


def validate_upload(
    *,
    filename: str | None,
    declared_content_type: str | None,
    data: bytes,
    allowed_extensions: set[str],
    max_size_bytes: int,
) -> ValidatedUpload:
    name = _validated_filename(filename)
    extension = _extension(name)

    if not data:
        raise UploadValidationError("The selected file is empty.")
    if len(data) > max_size_bytes:
        raise UploadValidationError(
            "The selected file is too large.",
            status_code=413,
        )
    if not extension or extension not in allowed_extensions:
        raise UploadValidationError("This file type is not allowed.", status_code=415)

    expected_mime = MIME_BY_EXTENSION.get(extension)
    if expected_mime is None:
        raise UploadValidationError("This file type is not allowed.", status_code=415)

    declared_mime = (declared_content_type or "").split(";", 1)[0].strip().lower()
    if not declared_mime:
        raise UploadValidationError("A file content type is required.", status_code=415)
    if declared_mime != expected_mime:
        raise UploadValidationError(
            "The declared file type does not match the file extension.",
            status_code=415,
        )
    if not _signature_matches(extension, data):
        raise UploadValidationError(
            "The file content does not match its declared type.",
            status_code=415,
        )

    return ValidatedUpload(
        name=name,
        extension=extension,
        mime_type=expected_mime,
        size=len(data),
        checksum=hashlib.sha256(data).hexdigest(),
        content=data,
    )
