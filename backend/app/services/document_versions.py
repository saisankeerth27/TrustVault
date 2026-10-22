"""Document content version persistence and replacement orchestration."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import AuditAction, AuditOutcome
from app.models.user import User
from app.services.audit import record_event
from app.services.documents import build_storage_key
from app.services.storage import (
    StorageConfigurationError,
    StorageObjectNotFoundError,
    StorageOperationError,
    SupabaseStorage,
)
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


class CurrentDocumentVersionDeletionError(Exception):
    """Raised when an attempt is made to delete the current version."""


class DocumentVersionDeletionError(Exception):
    """Raised when stored content cannot be safely deleted."""


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


def total_document_version_size(
    session: Session,
    *,
    document_id: UUID,
) -> int:
    return int(
        session.scalar(
            select(func.coalesce(func.sum(DocumentVersion.file_size), 0)).where(
                DocumentVersion.document_id == document_id
            )
        )
        or 0
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
    access_level: str | None = None,
    change_stats: dict[str, Any] | None = None,
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
        details: dict[str, Any] = {
            "change_summary": change_summary,
            "checksum": upload.checksum,
            "file_size": upload.size,
            "mime_type": upload.mime_type,
            "original_filename": upload.name,
            "previous_checksum": current.checksum,
            "previous_file_size": current.file_size,
            "previous_original_filename": current.original_filename,
            "previous_version_number": current.version_number,
            "resource_type": "DOCUMENT",
            "source": source,
            "version_number": version.version_number,
        }
        if access_level:
            details["access_level"] = access_level
        if change_stats:
            details["text_changes"] = change_stats
        record_event(
            session,
            action=AuditAction.DOCUMENT_VERSION_CREATED,
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            document_id=locked_document.id,
            details=details,
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


def delete_historical_version(
    session: Session,
    *,
    document: Document,
    version: DocumentVersion,
    actor: User,
    storage: SupabaseStorage,
    access_level: str,
) -> tuple[int, int, bool]:
    total_versions = int(
        session.scalar(
            select(func.count()).select_from(DocumentVersion).where(
                DocumentVersion.document_id == document.id
            )
        )
        or 0
    )
    if version.is_current or total_versions <= 1:
        raise CurrentDocumentVersionDeletionError

    deleted_version_number = version.version_number
    deleted_file_size = version.file_size
    storage_key = version.storage_key
    checksum = version.checksum
    original_filename = version.original_filename

    storage_deleted = False
    try:
        storage.delete_object(key=storage_key)
        storage_deleted = True
    except StorageObjectNotFoundError:
        logger.info("Document version object was already absent during deletion.")
    except (StorageConfigurationError, StorageOperationError) as exc:
        logger.error("Document version storage deletion failed.")
        raise DocumentVersionDeletionError(
            "The document version content could not be deleted."
        ) from exc
    except Exception as exc:
        logger.error("Document version storage deletion failed unexpectedly.")
        raise DocumentVersionDeletionError(
            "The document version content could not be deleted."
        ) from exc

    details: dict[str, Any] = {
        "checksum": checksum,
        "file_size": deleted_file_size,
        "original_filename": original_filename,
        "resource_type": "DOCUMENT",
        "storage_deleted": storage_deleted,
        "version_number": deleted_version_number,
        "access_level": access_level,
    }

    try:
        session.delete(version)
        record_event(
            session,
            action=AuditAction.DOCUMENT_VERSION_DELETE,
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            document_id=document.id,
            details=details,
        )
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error(
                "Database rollback failed after a document version deletion error."
            )
        logger.error(
            "Document version metadata deletion failed after its private object "
            "was removed; a retry can reconcile the remaining record."
        )
        raise DocumentVersionDeletionError(
            "The document version could not be fully deleted."
        ) from exc

    retained_total_size = total_document_version_size(
        session,
        document_id=document.id,
    )
    logger.info("Historical document version deleted by user %s.", actor.id)
    return deleted_file_size, retained_total_size, storage_deleted


def _delete_new_object(storage: SupabaseStorage, storage_key: str) -> None:
    try:
        storage.delete_object(key=storage_key)
    except Exception:
        logger.error(
            "A newly uploaded version object could not be cleaned up; "
            "the private object may require later cleanup."
        )
