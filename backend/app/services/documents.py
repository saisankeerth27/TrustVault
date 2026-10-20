"""Document metadata persistence and upload orchestration."""

from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.services.storage import WasabiStorage
from app.services.upload_validation import ValidatedUpload

logger = logging.getLogger(__name__)


class DocumentPersistenceError(Exception):
    """Raised when metadata cannot be committed after object storage succeeds."""


def build_storage_key(*, owner_id, extension: str) -> str:
    return f"documents/{owner_id}/{uuid4().hex}.{extension}"


def store_document(
    session: Session,
    *,
    owner: User,
    upload: ValidatedUpload,
    category: str | None,
    description: str | None,
    storage: WasabiStorage,
) -> Document:
    storage_key = build_storage_key(owner_id=owner.id, extension=upload.extension)

    storage.upload_bytes(
        key=storage_key,
        data=upload.content,
        content_type=upload.mime_type,
    )

    document = Document(
        owner_id=owner.id,
        name=upload.name,
        category=category,
        description=description,
        storage_key=storage_key,
        mime_type=upload.mime_type,
        file_size=upload.size,
        checksum=upload.checksum,
    )
    session.add(document)

    try:
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after a document upload error.")

        try:
            storage.delete_object(key=storage_key)
        except Exception:
            logger.error("Uploaded object cleanup failed after a database error.")

        logger.error("Document metadata persistence failed after object storage succeeded.")
        raise DocumentPersistenceError("The upload could not be completed.") from exc

    session.refresh(document)
    return document
