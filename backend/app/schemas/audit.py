from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AuditOutcome


class AuditEventResponse(BaseModel):
    id: UUID
    chain_index: int
    occurred_at: datetime
    actor_id: UUID | None
    actor_name: str | None
    document_id: UUID | None
    document_name: str | None
    action: str
    outcome: AuditOutcome
    request_id: str | None
    details: dict[str, Any]


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_previous: bool


class ChainIntegrityResponse(BaseModel):
    status: str
    event_count: int
    last_chain_index: int
    last_event_hash: str | None
    failure_chain_index: int | None
    message: str


class CheckpointIntegrityResponse(BaseModel):
    status: str
    last_chain_index: int | None
    created_at: str | None
    message: str


class AuditIntegrityResponse(BaseModel):
    status: str
    chain: ChainIntegrityResponse
    checkpoint: CheckpointIntegrityResponse
