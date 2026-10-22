"""Document metadata persistence, retrieval, and lifecycle orchestration."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.document_permission import DocumentPermission
from app.models.document_version import DocumentVersion
from app.models.enums import AuditAction, AuditOutcome
from app.models.user import User
from app.services.audit import record_event
from app.services.document_access import annotate_access_levels, visible_document_scope
from app.services.storage import (
    StorageConfigurationError,
    StorageObjectNotFoundError,
    StorageOperationError,
    SupabaseStorage,
)
from app.services.upload_validation import ValidatedUpload

logger = logging.getLogger(__name__)

_SORT_COLUMNS = {
    "name": func.lower(Document.name),
    "category": func.lower(Document.category),
    "file_size": Document.file_size,
    "created_at": Document.created_at,
    "updated_at": Document.updated_at,
}


class DocumentPersistenceError(Exception):
    """Raised when metadata cannot be committed after object storage succeeds."""


class DocumentUpdateError(Exception):
    """Raised when document metadata cannot be updated."""


class DocumentDeletionError(Exception):
    """Raised when a document cannot be logically deleted."""


def build_storage_key(*, owner_id, extension: str) -> str:
    return f"documents/{owner_id}/{uuid4().hex}.{extension}"


def store_document(
    session: Session,
    *,
    owner: User,
    upload: ValidatedUpload,
    category: str | None,
    description: str | None,
    storage: SupabaseStorage,
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
        session.flush()
        session.add(
            DocumentVersion(
                document_id=document.id,
                version_number=1,
                storage_key=storage_key,
                original_filename=upload.name,
                mime_type=upload.mime_type,
                file_size=upload.size,
                checksum=upload.checksum,
                uploaded_by=owner.id,
                change_summary="Initial upload",
                is_current=True,
            )
        )
        session.flush()
        record_event(
            session,
            action=AuditAction.DOCUMENT_UPLOAD,
            outcome=AuditOutcome.SUCCESS,
            actor=owner,
            document_id=document.id,
            details={
                "file_size": upload.size,
                "mime_type": upload.mime_type,
                "resource_type": "DOCUMENT",
                "version_number": 1,
            },
        )
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


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_documents(
    session: Session,
    *,
    user: User,
    q: str | None,
    category: str | None,
    owner_id: UUID | None,
    created_from: date | None,
    created_to: date | None,
    page: int,
    page_size: int,
    sort_by: str,
    order: str,
) -> tuple[list[Document], int]:
    conditions = [Document.deleted_at.is_(None), *visible_document_scope(user)]

    if q:
        conditions.append(
            Document.name.ilike(f"%{_escape_like(q)}%", escape="\\")
        )
    if category:
        conditions.append(func.lower(Document.category) == category.lower())
    if owner_id is not None:
        conditions.append(Document.owner_id == owner_id)
    if created_from is not None:
        conditions.append(
            Document.created_at
            >= datetime.combine(created_from, time.min, tzinfo=timezone.utc)
        )
    if created_to is not None:
        conditions.append(
            Document.created_at
            < datetime.combine(
                created_to + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
        )

    total = session.scalar(
        select(func.count()).select_from(Document).where(*conditions)
    )
    sort_column = _SORT_COLUMNS[sort_by]
    direction = sort_column.asc() if order == "asc" else sort_column.desc()

    documents = list(
        session.scalars(
            select(Document)
            .where(*conditions)
            .options(selectinload(Document.owner))
            .order_by(direction, Document.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    annotate_access_levels(session, user=user, documents=documents)
    return documents, int(total or 0)


def list_shared_documents(
    session: Session,
    *,
    user: User,
    page: int,
    page_size: int,
    sort_by: str,
    order: str,
) -> tuple[list[Document], int]:
    conditions = [
        Document.deleted_at.is_(None),
        DocumentPermission.user_id == user.id,
        DocumentPermission.revoked_at.is_(None),
    ]
    total = session.scalar(
        select(func.count())
        .select_from(Document)
        .join(DocumentPermission, DocumentPermission.document_id == Document.id)
        .where(*conditions)
    )
    sort_column = _SORT_COLUMNS[sort_by]
    direction = sort_column.asc() if order == "asc" else sort_column.desc()

    documents = list(
        session.scalars(
            select(Document)
            .join(DocumentPermission, DocumentPermission.document_id == Document.id)
            .where(*conditions)
            .options(selectinload(Document.owner))
            .order_by(direction, Document.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    annotate_access_levels(session, user=user, documents=documents)
    return documents, int(total or 0)


def update_document_metadata(
    session: Session,
    *,
    document: Document,
    changes: dict[str, object],
    actor: User,
) -> Document:
    for field in ("name", "category", "description"):
        if field in changes:
            setattr(document, field, changes[field])

    try:
        record_event(
            session,
            action=AuditAction.DOCUMENT_METADATA_UPDATE,
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            document_id=document.id,
            details={
                "changed_fields": sorted(changes),
                "resource_type": "DOCUMENT",
            },
        )
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after a document update error.")
        logger.error("Document metadata update failed.")
        raise DocumentUpdateError("The document could not be updated.") from exc

    session.refresh(document)
    return document


def soft_delete_document(
    session: Session,
    *,
    document: Document,
    actor: User,
    storage: SupabaseStorage,
) -> None:
    document.deleted_at = datetime.now(timezone.utc)
    version_keys = list(
        session.scalars(
            select(DocumentVersion.storage_key).where(
                DocumentVersion.document_id == document.id
            )
        ).all()
    )
    storage_keys = list(dict.fromkeys([document.storage_key, *version_keys]))

    try:
        record_event(
            session,
            action=AuditAction.DOCUMENT_DELETE,
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            document_id=document.id,
            details={"resource_type": "DOCUMENT"},
        )
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after a document deletion error.")
        logger.error("Document soft deletion failed.")
        raise DocumentDeletionError("The document could not be deleted.") from exc

    for storage_key in storage_keys:
        try:
            storage.delete_object(key=storage_key)
        except StorageObjectNotFoundError:
            logger.info("Document object was already absent during deletion.")
        except (StorageConfigurationError, StorageOperationError):
            logger.error(
                "Document object cleanup failed after soft deletion; "
                "the private object may require later cleanup."
            )
        except Exception:
            logger.error(
                "Document object cleanup failed unexpectedly after soft deletion; "
                "the private object may require later cleanup."
            )
