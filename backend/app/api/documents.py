from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import get_settings
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.services.documents import DocumentPersistenceError, store_document
from app.services.storage import (
    StorageConfigurationError,
    StorageOperationError,
    WasabiStorage,
    get_storage_service,
)
from app.services.upload_validation import (
    UploadValidationError,
    normalize_optional_text,
    validate_upload,
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

require_document_uploader = require_roles(
    UserRole.ADMINISTRATOR,
    UserRole.DOCUMENT_OWNER,
)

_CONTENT_LENGTH_OVERHEAD_BYTES = 1024 * 1024


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

    if declared_length > max_size_bytes + _CONTENT_LENGTH_OVERHEAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The selected file is too large.",
        )


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description=(
        "Stores a validated document in private Wasabi storage and records its metadata. "
        "Only active Administrators and Document owners may upload."
    ),
)
def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    category: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    current_user: User = Depends(require_document_uploader),
    session: Session = Depends(get_db),
    storage: WasabiStorage = Depends(get_storage_service),
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

    return DocumentResponse.model_validate(document)
