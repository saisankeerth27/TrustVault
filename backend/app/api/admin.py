from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.models.enums import AuditAction, AuditOutcome, UserRole
from app.models.user import User
from app.schemas.audit import (
    AuditEventListResponse,
    AuditEventResponse,
    AuditIntegrityResponse,
    ChainIntegrityResponse,
    CheckpointIntegrityResponse,
)
from app.services.audit import record_best_effort
from app.services.audit_integrity import verify_audit_trail

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _access_denied() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to access this resource.",
    )


def require_audit_administrator(
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


def _event_response(event: AuditEvent) -> AuditEventResponse:
    actor_name = event.actor.name if event.actor is not None else None
    if actor_name is None:
        stored_actor_name = event.details.get("actor_name")
        actor_name = stored_actor_name if isinstance(stored_actor_name, str) else None

    return AuditEventResponse(
        id=event.id,
        chain_index=event.chain_index,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        actor_name=actor_name,
        document_id=event.document_id,
        document_name=event.document.name if event.document is not None else None,
        action=event.action,
        outcome=event.outcome,
        request_id=event.request_id,
        details=event.details,
    )


@router.get("/audit-events", response_model=AuditEventListResponse)
def list_audit_events(
    response: Response,
    actor_id: UUID | None = None,
    document_id: UUID | None = None,
    action: AuditAction | None = None,
    outcome: AuditOutcome | None = None,
    occurred_from: date | None = None,
    occurred_to: date | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    current_user: User = Depends(require_audit_administrator),
    session: Session = Depends(get_db),
) -> AuditEventListResponse:
    del current_user
    _validate_date_range(occurred_from, occurred_to)

    conditions = []
    if actor_id is not None:
        conditions.append(AuditEvent.actor_id == actor_id)
    if document_id is not None:
        conditions.append(AuditEvent.document_id == document_id)
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
        items=[_event_response(event) for event in events],
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
    current_user: User = Depends(require_audit_administrator),
    session: Session = Depends(get_db),
) -> AuditIntegrityResponse:
    del current_user
    verification = verify_audit_trail(session, settings=get_settings())
    response.headers["Cache-Control"] = "no-store"

    return AuditIntegrityResponse(
        status=verification.status,
        chain=ChainIntegrityResponse(
            status=verification.chain.status,
            event_count=verification.chain.event_count,
            last_chain_index=verification.chain.last_chain_index,
            last_event_hash=verification.chain.last_event_hash,
            failure_chain_index=verification.chain.failure_chain_index,
            message=verification.chain.message,
        ),
        checkpoint=CheckpointIntegrityResponse(
            status=verification.checkpoint.status,
            last_chain_index=verification.checkpoint.last_chain_index,
            created_at=verification.checkpoint.created_at,
            message=verification.checkpoint.message,
        ),
    )
