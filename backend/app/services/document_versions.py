"""Document content version persistence and replacement orchestration."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import AuditAction, AuditOutcome
from app.models.user import User
from app.services.audit import record_event
from app.services.documents import build_storage_key
from app.services.storage import SupabaseStorage
from app.services.upload_validation import ValidatedUpload

logger = logging.getLogger(__name__)


class DocumentVersionNotFoundError(Exception):
    """Raised when a document version is missing or no longer visible."""


class DocumentVersionConflictError(Exception):
    """Raised when a replacement is based on an outdated current version."""

    def __init__(self, current_version_number: int) -> None:
        super().__init__("The document has changed since it was loaded.")
        self.current_version_number = current_version_number


class DocumentVersionOperationError(Exception):
    """Raised when a new version cannot be persisted."""


def get_current_version(
    session: Session,
    *,
    document_id: UUID,
    for_update: bool = False,
) -> DocumentVersion | None:
    statement = (
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.is_current.is_(True),
        )
        .options(selectinload(DocumentVersion.uploader))
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def list_document_versions(
    session: Session,
    *,
    document: Document,
) -> list[DocumentVersion]:
    return list(
        session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .options(selectinload(DocumentVersion.uploader))
            .order_by(DocumentVersion.version_number.desc())
        ).all()
    )


def get_document_version(
    session: Session,
    *,
    document: Document,
    version_number: int,
) -> DocumentVersion:
    version = session.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == version_number,
        )
        .options(selectinload(DocumentVersion.uploader))
    )
    if version is None:
        raise DocumentVersionNotFoundError
    return version


def replace_document_version(
    session: Session,
    *,
    document: Document,
    upload: ValidatedUpload,
    expected_version_number: int,
    change_summary: str | None,
    actor: User,
    storage: SupabaseStorage,
    source: str,
) -> tuple[Document, DocumentVersion]:
    current = get_current_version(session, document_id=document.id)
    if current is None:
        raise DocumentVersionNotFoundError
    if current.version_number != expected_version_number:
        raise DocumentVersionConflictError(current.version_number)

    storage_key = build_storage_key(
        owner_id=document.owner_id,
        extension=upload.extension,
    )
    storage.upload_bytes(
        key=storage_key,
        data=upload.content,
        content_type=upload.mime_type,
    )

    locked_document = session.scalar(
        select(Document)
        .where(
            Document.id == document.id,
            Document.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if locked_document is None:
        _delete_new_object(storage, storage_key)
        raise DocumentVersionNotFoundError

    current = get_current_version(
        session,
        document_id=locked_document.id,
        for_update=True,
    )
    if current is None:
        _delete_new_object(storage, storage_key)
        raise DocumentVersionNotFoundError
    if current.version_number != expected_version_number:
        current_number = current.version_number
        _delete_new_object(storage, storage_key)
        raise DocumentVersionConflictError(current_number)

    current.is_current = False
    session.flush()

    version = DocumentVersion(
        document_id=locked_document.id,
        version_number=current.version_number + 1,
        storage_key=storage_key,
        original_filename=upload.name,
        mime_type=upload.mime_type,
        file_size=upload.size,
        checksum=upload.checksum,
        uploaded_by=actor.id,
        change_summary=change_summary,
        is_current=True,
    )
    session.add(version)

    locked_document.storage_key = storage_key
    locked_document.mime_type = upload.mime_type
    locked_document.file_size = upload.size
    locked_document.checksum = upload.checksum

    try:
        session.flush()
        record_event(
            session,
            action=AuditAction.DOCUMENT_VERSION_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            document_id=locked_document.id,
            details={
                "change_summary": change_summary,
                "file_size": upload.size,
                "mime_type": upload.mime_type,
                "previous_version_number": current.version_number,
                "resource_type": "DOCUMENT",
                "source": source,
                "version_number": version.version_number,
            },
        )
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after a version replacement error.")

        _delete_new_object(storage, storage_key)
        logger.error("Document version persistence failed.")
        raise DocumentVersionOperationError(
            "The new document version could not be saved."
        ) from exc

    session.refresh(locked_document)
    session.refresh(version)
    logger.info(
        "Document version created for user %s.",
        actor.id,
    )
    return locked_document, version


def _delete_new_object(storage: SupabaseStorage, storage_key: str) -> None:
    try:
        storage.delete_object(key=storage_key)
    except Exception:
        logger.error(
            "A newly uploaded version object could not be cleaned up; "
            "the private object may require later cleanup."
        )
