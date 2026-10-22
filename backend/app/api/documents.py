from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterator
from datetime import date
from typing import IO, Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.request_limits import UPLOAD_CONTENT_LENGTH_OVERHEAD_BYTES
from app.db.session import get_db
from app.models.document_permission import DocumentPermission
from app.models.enums import AuditAction, AuditOutcome, DocumentAccessLevel
from app.models.user import User
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
    PermissionGrantRequest,
    PermissionListResponse,
    PermissionResponse,
    PermissionUpdateRequest,
)
from app.services.audit import record_best_effort, record_event
from app.services.document_access import (
    DocumentAccessDeniedError,
    DocumentCapability,
    DocumentNotFoundError,
    authorize_document,
)
from app.services.documents import (
    DocumentDeletionError,
    DocumentPersistenceError,
    DocumentUpdateError,
    list_documents,
    list_shared_documents,
    soft_delete_document,
    store_document,
    update_document_metadata,
)
from app.services.permissions import (
    PermissionAlreadyExistsError,
    PermissionNotFoundError,
    PermissionOperationError,
    PermissionRecipientIsOwnerError,
    PermissionRecipientNotFoundError,
    grant_permission,
    list_permissions,
    revoke_permission,
    update_permission,
)
from app.services.storage import (
    StorageConfigurationError,
    StorageObjectNotFoundError,
    StorageOperationError,
    SupabaseStorage,
    get_storage_service,
)
from app.services.upload_validation import (
    UploadValidationError,
    normalize_optional_text,
    validate_upload,
)

logger = logging.getLogger("trustvault.documents")

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

_DOWNLOAD_CHUNK_SIZE = 64 * 1024
_NOT_FOUND_MESSAGE = "Document not found."


def _document_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_NOT_FOUND_MESSAGE,
    )


def _access_denied() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to perform this action.",
    )


def _permission_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Permission not found.",
    )


def _permission_response(record: DocumentPermission) -> PermissionResponse:
    return PermissionResponse(
        id=record.id,
        document_id=record.document_id,
        user_id=record.user_id,
        recipient_name=record.user.name,
        recipient_email=record.user.email,
        permission=record.permission,
        granted_at=record.created_at,
        revoked_at=record.revoked_at,
        status="ACTIVE" if record.revoked_at is None else "REVOKED",
    )


def _document_list_response(
    documents: list,
    *,
    total: int,
    page: int,
    page_size: int,
) -> DocumentListResponse:
    pages = (total + page_size - 1) // page_size
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(document) for document in documents],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_previous=page > 1 and pages > 0,
    )


def _validate_date_range(
    created_from: date | None,
    created_to: date | None,
) -> None:
    if created_from and created_to and created_from > created_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="created_from must be on or before created_to.",
        )


def _safe_fallback_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKD", filename).encode(
        "ascii", "ignore"
    ).decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", normalized).strip(" .")
    return (safe or "download")[:120]


def _content_disposition(filename: str) -> str:
    fallback = _safe_fallback_filename(filename)
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def _stream_body(body: IO[bytes]) -> Iterator[bytes]:
    try:
        while chunk := body.read(_DOWNLOAD_CHUNK_SIZE):
            yield chunk
    finally:
        body.close()


def _enforce_request_size(request: Request, max_size_bytes: int) -> None:
    content_length = request.headers.get("content-length")
    if content_length is None:
        return

    try:
        declared_length = int(content_length)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The Content-Length header is invalid.",
        ) from exc

    if declared_length > max_size_bytes + UPLOAD_CONTENT_LENGTH_OVERHEAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The selected file is too large.",
        )


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description=(
        "Stores a validated document in private Supabase Storage and records its metadata. "
        "Any active user may upload and becomes the document owner."
    ),
)
def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    category: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: SupabaseStorage = Depends(get_storage_service),
) -> DocumentResponse:
    settings = get_settings()
    _enforce_request_size(request, settings.max_upload_size_bytes)

    try:
        data = file.file.read(settings.max_upload_size_bytes + 1)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file could not be read.",
        ) from exc

    try:
        upload = validate_upload(
            filename=file.filename,
            declared_content_type=file.content_type,
            data=data,
            allowed_extensions=settings.allowed_upload_extension_set,
            max_size_bytes=settings.max_upload_size_bytes,
        )
        normalized_category = normalize_optional_text(
            category,
            field="Category",
            max_length=100,
        )
        normalized_description = normalize_optional_text(
            description,
            field="Description",
            max_length=2000,
        )
    except UploadValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc

    try:
        document = store_document(
            session,
            owner=current_user,
            upload=upload,
            category=normalized_category,
            description=normalized_description,
            storage=storage,
        )
    except StorageConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is not configured.",
        ) from exc
    except StorageOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is temporarily unavailable.",
        ) from exc
    except DocumentPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The upload could not be completed.",
        ) from exc

    document.access_level = DocumentAccessLevel.OWNER.value
    return DocumentResponse.model_validate(document)


@router.get("", response_model=DocumentListResponse)
def list_document_metadata(
    q: Annotated[str | None, Query(max_length=255)] = None,
    category: Annotated[str | None, Query(max_length=100)] = None,
    owner_id: UUID | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Literal[
        "name",
        "category",
        "file_size",
        "created_at",
        "updated_at",
    ] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DocumentListResponse:
    _validate_date_range(created_from, created_to)
    normalized_query = q.strip() if q else None
    normalized_category = category.strip() if category else None

    documents, total = list_documents(
        session,
        user=current_user,
        q=normalized_query or None,
        category=normalized_category or None,
        owner_id=owner_id,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )

    pages = (total + page_size - 1) // page_size
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(document) for document in documents],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_previous=page > 1 and pages > 0,
    )


@router.get("/shared-with-me", response_model=DocumentListResponse)
def list_shared_with_me(
    response: Response,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Literal[
        "name",
        "category",
        "file_size",
        "created_at",
        "updated_at",
    ] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DocumentListResponse:
    documents, total = list_shared_documents(
        session,
        user=current_user,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )
    response.headers["Cache-Control"] = "no-store"
    return _document_list_response(
        documents,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document_metadata(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DocumentResponse:
    try:
        authorized = authorize_document(
            session,
            user=current_user,
            document_id=document_id,
            capability=DocumentCapability.METADATA,
        )
    except DocumentNotFoundError as exc:
        logger.warning("Document metadata access denied for user %s.", current_user.id)
        raise _document_not_found() from exc
    except DocumentAccessDeniedError as exc:
        logger.warning("Document metadata access denied for user %s.", current_user.id)
        raise _access_denied() from exc

    return DocumentResponse.model_validate(authorized.document)


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: UUID,
    payload: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DocumentResponse:
    try:
        authorized = authorize_document(
            session,
            user=current_user,
            document_id=document_id,
            capability=DocumentCapability.EDIT,
        )
    except DocumentNotFoundError as exc:
        logger.warning("Document metadata update denied for user %s.", current_user.id)
        raise _document_not_found() from exc
    except DocumentAccessDeniedError as exc:
        logger.warning("Document metadata update denied for user %s.", current_user.id)
        raise _access_denied() from exc

    try:
        updated = update_document_metadata(
            session,
            document=authorized.document,
            changes=payload.model_dump(exclude_unset=True),
            actor=current_user,
        )
    except DocumentUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The document could not be updated.",
        ) from exc

    updated.access_level = authorized.access_level.value
    logger.info(
        "Document metadata updated by user %s.",
        current_user.id,
    )
    return DocumentResponse.model_validate(updated)


@router.get("/{document_id}/download")
def download_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: SupabaseStorage = Depends(get_storage_service),
) -> StreamingResponse:
    try:
        authorized = authorize_document(
            session,
            user=current_user,
            document_id=document_id,
            capability=DocumentCapability.READ,
        )
    except DocumentNotFoundError as exc:
        logger.warning("Document download denied for user %s.", current_user.id)
        raise _document_not_found() from exc
    except DocumentAccessDeniedError as exc:
        logger.warning("Document download denied for user %s.", current_user.id)
        raise _access_denied() from exc

    document = authorized.document
    try:
        body = storage.open_download(key=document.storage_key)
    except StorageObjectNotFoundError as exc:
        logger.warning("Document object was not found during download.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document content is unavailable.",
        ) from exc
    except StorageConfigurationError as exc:
        logger.error("Document storage is not configured for download.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is not configured.",
        ) from exc
    except StorageOperationError as exc:
        logger.error("Document storage failed during download.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is temporarily unavailable.",
        ) from exc

    try:
        record_event(
            session,
            action=AuditAction.DOCUMENT_DOWNLOAD,
            outcome=AuditOutcome.SUCCESS,
            actor=current_user,
            document_id=document.id,
            details={
                "file_size": document.file_size,
                "resource_type": "DOCUMENT",
            },
        )
        session.commit()
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after a download audit error.")
        body.close()
        logger.error("Document download audit event could not be recorded.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The download could not be completed.",
        ) from exc

    logger.info(
        "Document download started for user %s.",
        current_user.id,
    )
    return StreamingResponse(
        _stream_body(body),
        media_type=document.mime_type,
        headers={
            "Content-Disposition": _content_disposition(document.name),
            "Content-Length": str(document.file_size),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    storage: SupabaseStorage = Depends(get_storage_service),
) -> Response:
    try:
        authorized = authorize_document(
            session,
            user=current_user,
            document_id=document_id,
            capability=DocumentCapability.DELETE,
        )
    except DocumentNotFoundError as exc:
        logger.warning("Document deletion denied for user %s.", current_user.id)
        raise _document_not_found() from exc
    except DocumentAccessDeniedError as exc:
        logger.warning("Document deletion denied for user %s.", current_user.id)
        raise _access_denied() from exc

    try:
        soft_delete_document(
            session,
            document=authorized.document,
            actor=current_user,
            storage=storage,
        )
    except DocumentDeletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The document could not be deleted.",
        ) from exc

    logger.info(
        "Document soft-deleted by user %s.",
        current_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

def _require_permission_manager(
    session: Session,
    *,
    current_user: User,
    document_id: UUID,
):
    try:
        return authorize_document(
            session,
            user=current_user,
            document_id=document_id,
            capability=DocumentCapability.MANAGE_PERMISSIONS,
        )
    except DocumentNotFoundError as exc:
        logger.warning("Document permission access denied for user %s.", current_user.id)
        raise _document_not_found() from exc
    except DocumentAccessDeniedError as exc:
        logger.warning("Document permission access denied for user %s.", current_user.id)
        raise _access_denied() from exc


@router.get(
    "/{document_id}/permissions",
    response_model=PermissionListResponse,
)
def list_document_permissions(
    document_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PermissionListResponse:
    authorized = _require_permission_manager(
        session,
        current_user=current_user,
        document_id=document_id,
    )
    records = list_permissions(session, document=authorized.document)
    response.headers["Cache-Control"] = "no-store"
    return PermissionListResponse(
        items=[_permission_response(record) for record in records],
        total=len(records),
        active_total=sum(record.revoked_at is None for record in records),
    )


@router.post(
    "/{document_id}/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def grant_document_permission(
    document_id: UUID,
    payload: PermissionGrantRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PermissionResponse:
    authorized = _require_permission_manager(
        session,
        current_user=current_user,
        document_id=document_id,
    )

    try:
        record, created = grant_permission(
            session,
            document=authorized.document,
            recipient_email=str(payload.email),
            permission=payload.permission,
            granted_by=current_user,
        )
    except PermissionRecipientNotFoundError as exc:
        logger.warning("Permission grant rejected for an unavailable recipient.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient account is not available.",
        ) from exc
    except PermissionRecipientIsOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The document owner already has access.",
        ) from exc
    except PermissionAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active permission already exists; update it instead.",
        ) from exc
    except PermissionOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The permission could not be granted.",
        ) from exc

    if not created:
        response.status_code = status.HTTP_200_OK
    response.headers["Cache-Control"] = "no-store"
    logger.info("Document permission granted by user %s.", current_user.id)
    return _permission_response(record)


@router.patch(
    "/{document_id}/permissions/{permission_id}",
    response_model=PermissionResponse,
)
def update_document_permission(
    document_id: UUID,
    permission_id: UUID,
    payload: PermissionUpdateRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PermissionResponse:
    authorized = _require_permission_manager(
        session,
        current_user=current_user,
        document_id=document_id,
    )

    try:
        record, changed = update_permission(
            session,
            document=authorized.document,
            permission_id=permission_id,
            permission=payload.permission,
            updated_by=current_user,
        )
    except PermissionNotFoundError as exc:
        raise _permission_not_found() from exc
    except PermissionOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The permission could not be updated.",
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "Document permission %s by user %s.",
        "updated" if changed else "unchanged",
        current_user.id,
    )
    return _permission_response(record)


@router.delete(
    "/{document_id}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_document_permission(
    document_id: UUID,
    permission_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    authorized = _require_permission_manager(
        session,
        current_user=current_user,
        document_id=document_id,
    )

    try:
        changed = revoke_permission(
            session,
            document=authorized.document,
            permission_id=permission_id,
            revoked_by=current_user,
        )
    except PermissionNotFoundError as exc:
        raise _permission_not_found() from exc
    except PermissionOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The permission could not be revoked.",
        ) from exc

    logger.info(
        "Document permission %s by user %s.",
        "revoked" if changed else "already revoked",
        current_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
