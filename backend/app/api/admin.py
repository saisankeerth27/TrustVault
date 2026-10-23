from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.models.document_permission import DocumentPermission
from app.models.enums import AuditAction, AuditOutcome, UserRole, UserStatus
from app.models.user import User
from app.schemas.admin import (
    AdminAccountChangeResponse,
    AdminSummaryResponse,
    AdminUserListResponse,
    AdminUserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)
from app.schemas.audit import (
    AuditEventListResponse,
    AuditIntegrityResponse,
    ChainIntegrityResponse,
    CheckpointIntegrityResponse,
)
from app.schemas.document import PermissionListResponse, PermissionResponse
from app.services.admin_accounts import (
    AdminAccountNotFoundError,
    AdminAccountOperationError,
    LastActiveAdministratorError,
    SelfAccountChangeError,
    update_account_role,
    update_account_status,
)
from app.services.audit import record_best_effort
from app.services.audit_integrity import verify_audit_trail
from app.services.audit_presenter import audit_event_response
from app.services.permissions import list_permissions

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _access_denied() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to access this resource.",
    )


def require_admin_access(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> User:
    if current_user.role != UserRole.ADMINISTRATOR.value:
        record_best_effort(
            session,
            action=AuditAction.AUDIT_ACCESS_DENIED,
            outcome=AuditOutcome.DENIED,
            actor=current_user,
            details={
                "reason": "role_not_permitted",
                "role": current_user.role,
                "resource_type": "ADMIN",
            },
        )
        raise _access_denied()
    return current_user


def _validate_date_range(
    occurred_from: date | None,
    occurred_to: date | None,
) -> None:
    if occurred_from and occurred_to and occurred_from > occurred_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="occurred_from must be on or before occurred_to.",
        )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _document_count(session: Session, user_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.owner_id == user_id,
                Document.deleted_at.is_(None),
            )
        )
        or 0
    )


def _admin_user_response(user: User, document_count: int) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        status=user.status,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
        document_count=document_count,
    )


def _admin_permission_response(record: DocumentPermission) -> PermissionResponse:
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


def _account_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AdminAccountNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )
    if isinstance(exc, SelfAccountChangeError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Administrators cannot change their own role or status.",
        )
    if isinstance(exc, LastActiveAdministratorError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one active administrator must remain.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="The account could not be updated.",
    )


def _record_account_change_denial(
    session: Session,
    *,
    actor: User,
    target_user_id: UUID,
    action: AuditAction,
    reason: str,
) -> None:
    record_best_effort(
        session,
        action=action,
        outcome=AuditOutcome.DENIED,
        actor=actor,
        details={
            "reason": reason,
            "target_user_id": str(target_user_id),
            "resource_type": "USER",
        },
    )


@router.get("/summary", response_model=AdminSummaryResponse)
def get_admin_summary(
    response: Response,
    current_user: User = Depends(require_admin_access),
    session: Session = Depends(get_db),
) -> AdminSummaryResponse:
    del current_user
    total_users = int(
        session.scalar(select(func.count()).select_from(User)) or 0
    )
    active_users = int(
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.status == UserStatus.ACTIVE.value)
        )
        or 0
    )
    administrators = int(
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMINISTRATOR.value)
        )
        or 0
    )
    active_documents = int(
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.deleted_at.is_(None))
        )
        or 0
    )
    deleted_documents = int(
        session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.deleted_at.is_not(None))
        )
        or 0
    )
    active_grants = int(
        session.scalar(
            select(func.count())
            .select_from(DocumentPermission)
            .where(DocumentPermission.revoked_at.is_(None))
        )
        or 0
    )

    response.headers["Cache-Control"] = "no-store"
    return AdminSummaryResponse(
        total_users=total_users,
        active_users=active_users,
        disabled_users=total_users - active_users,
        administrators=administrators,
        normal_users=total_users - administrators,
        active_documents=active_documents,
        deleted_documents=deleted_documents,
        active_grants=active_grants,
    )


@router.get("/users", response_model=AdminUserListResponse)
def list_admin_users(
    response: Response,
    q: Annotated[str | None, Query(max_length=255)] = None,
    status_filter: Annotated[
        UserStatus | None,
        Query(alias="status"),
    ] = None,
    role: UserRole | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    current_user: User = Depends(require_admin_access),
    session: Session = Depends(get_db),
) -> AdminUserListResponse:
    del current_user
    conditions = []
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        conditions.append(
            or_(
                User.name.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
            )
        )
    if status_filter is not None:
        conditions.append(User.status == status_filter.value)
    if role is not None:
        conditions.append(User.role == role.value)

    total = int(
        session.scalar(
            select(func.count()).select_from(User).where(*conditions)
        )
        or 0
    )
    document_count = (
        select(func.count())
        .select_from(Document)
        .where(
            Document.owner_id == User.id,
            Document.deleted_at.is_(None),
        )
        .correlate(User)
        .scalar_subquery()
    )
    rows = session.execute(
        select(User, document_count.label("document_count"))
        .where(*conditions)
        .order_by(User.created_at.desc(), User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    pages = (total + page_size - 1) // page_size
    response.headers["Cache-Control"] = "no-store"
    return AdminUserListResponse(
        items=[
            _admin_user_response(user, int(count or 0))
            for user, count in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_previous=page > 1 and pages > 0,
    )


@router.get("/users/{user_id}", response_model=AdminUserResponse)
def get_admin_user(
    user_id: UUID,
    response: Response,
    current_user: User = Depends(require_admin_access),
    session: Session = Depends(get_db),
) -> AdminUserResponse:
    del current_user
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )
    response.headers["Cache-Control"] = "no-store"
    return _admin_user_response(user, _document_count(session, user.id))


@router.patch("/users/{user_id}/status", response_model=AdminAccountChangeResponse)
def change_user_status(
    user_id: UUID,
    payload: UserStatusUpdateRequest,
    current_user: User = Depends(require_admin_access),
    session: Session = Depends(get_db),
) -> AdminAccountChangeResponse:
    try:
        user, changed = update_account_status(
            session,
            actor=current_user,
            target_user_id=user_id,
            status=payload.status,
        )
    except (
        AdminAccountNotFoundError,
        SelfAccountChangeError,
        LastActiveAdministratorError,
        AdminAccountOperationError,
    ) as exc:
        if not isinstance(exc, AdminAccountOperationError):
            _record_account_change_denial(
                session,
                actor=current_user,
                target_user_id=user_id,
                action=AuditAction.USER_STATUS_CHANGED,
                reason=type(exc).__name__,
            )
        raise _account_error(exc) from exc

    return AdminAccountChangeResponse(
        user=_admin_user_response(
            user,
            _document_count(session, user.id),
        ),
        changed=changed,
    )


@router.patch("/users/{user_id}/role", response_model=AdminAccountChangeResponse)
def change_user_role(
    user_id: UUID,
    payload: UserRoleUpdateRequest,
    current_user: User = Depends(require_admin_access),
    session: Session = Depends(get_db),
) -> AdminAccountChangeResponse:
    try:
        user, changed = update_account_role(
            session,
            actor=current_user,
            target_user_id=user_id,
            role=payload.role,
        )
    except (
        AdminAccountNotFoundError,
        SelfAccountChangeError,
        LastActiveAdministratorError,
        AdminAccountOperationError,
    ) as exc:
        if not isinstance(exc, AdminAccountOperationError):
            _record_account_change_denial(
                session,
                actor=current_user,
                target_user_id=user_id,
                action=AuditAction.USER_ROLE_CHANGED,
                reason=type(exc).__name__,
            )
        raise _account_error(exc) from exc

    return AdminAccountChangeResponse(
        user=_admin_user_response(
            user,
            _document_count(session, user.id),
        ),
        changed=changed,
    )


@router.get(
    "/documents/{document_id}/permissions",
    response_model=PermissionListResponse,
)
def list_document_permission_oversight(
    document_id: UUID,
    response: Response,
    current_user: User = Depends(require_admin_access),
    session: Session = Depends(get_db),
) -> PermissionListResponse:
    del current_user
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    records = list_permissions(session, document=document)
    response.headers["Cache-Control"] = "no-store"
    return PermissionListResponse(
        items=[_admin_permission_response(record) for record in records],
        total=len(records),
        active_total=sum(record.revoked_at is None for record in records),
    )


@router.get("/audit-events", response_model=AuditEventListResponse)
def list_audit_events(
    response: Response,
    actor_id: UUID | None = None,
    target_user_id: UUID | None = None,
    document_id: UUID | None = None,
    resource_type: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    action: AuditAction | None = None,
    outcome: AuditOutcome | None = None,
    occurred_from: date | None = None,
    occurred_to: date | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    current_user: User = Depends(require_admin_access),
    session: Session = Depends(get_db),
) -> AuditEventListResponse:
    del current_user
    _validate_date_range(occurred_from, occurred_to)

    conditions = []
    if actor_id is not None:
        conditions.append(AuditEvent.actor_id == actor_id)
    if target_user_id is not None:
        conditions.append(
            AuditEvent.details["target_user_id"].astext == str(target_user_id)
        )
    if document_id is not None:
        conditions.append(AuditEvent.document_id == document_id)
    if resource_type is not None:
        conditions.append(
            func.lower(AuditEvent.details["resource_type"].astext)
            == resource_type.strip().lower()
        )
    if action is not None:
        conditions.append(AuditEvent.action == action.value)
    if outcome is not None:
        conditions.append(AuditEvent.outcome == outcome.value)
    if occurred_from is not None:
        conditions.append(
            AuditEvent.occurred_at
            >= datetime.combine(occurred_from, time.min, tzinfo=timezone.utc)
        )
    if occurred_to is not None:
        conditions.append(
            AuditEvent.occurred_at
            < datetime.combine(
                occurred_to + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
        )

    total = int(
        session.scalar(
            select(func.count()).select_from(AuditEvent).where(*conditions)
        )
        or 0
    )
    events = list(
        session.scalars(
            select(AuditEvent)
            .where(*conditions)
            .options(
                selectinload(AuditEvent.actor),
                selectinload(AuditEvent.document),
            )
            .order_by(AuditEvent.chain_index.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )

    pages = (total + page_size - 1) // page_size
    response.headers["Cache-Control"] = "no-store"
    return AuditEventListResponse(
        items=[audit_event_response(event) for event in events],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_previous=page > 1 and pages > 0,
    )


@router.get("/audit-integrity", response_model=AuditIntegrityResponse)
def get_audit_integrity(
    response: Response,
    current_user: User = Depends(require_admin_access),
    session: Session = Depends(get_db),
) -> AuditIntegrityResponse:
    del current_user
    verification = verify_audit_trail(session, settings=get_settings())
    response.headers["Cache-Control"] = "no-store"

    return AuditIntegrityResponse(
        status=verification.status,
        verified_at=datetime.now(timezone.utc),
        chain=ChainIntegrityResponse(
            status=verification.chain.status,
            event_count=verification.chain.event_count,
            last_chain_index=verification.chain.last_chain_index,
            last_event_hash=verification.chain.last_event_hash,
            failure_chain_index=verification.chain.failure_chain_index,
            message=verification.chain.message,
            legacy_skipped=verification.chain.legacy_skipped,
        ),
        checkpoint=CheckpointIntegrityResponse(
            status=verification.checkpoint.status,
            last_chain_index=verification.checkpoint.last_chain_index,
            created_at=verification.checkpoint.created_at,
            message=verification.checkpoint.message,
        ),
    )
