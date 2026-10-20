"""Central tamper-evident audit event writer."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from math import isfinite
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.request_context import get_request_id, get_request_metadata
from app.models.audit_event import AuditEvent
from app.models.enums import AuditAction, AuditOutcome
from app.models.user import User

logger = logging.getLogger(__name__)

AUDIT_HASH_SCHEMA = "trustvault-audit-event-v1"
_AUDIT_CHAIN_LOCK_ID = 0x54525641554C54
_MAX_DETAILS_BYTES = 8 * 1024
_MAX_DETAIL_DEPTH = 5
_MAX_LIST_ITEMS = 100

_DETAIL_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "session_id",
    "content",
    "payload",
)


class AuditWriteError(Exception):
    """Raised when a mandatory audit event cannot be persisted."""


class AuditMetadataError(ValueError):
    """Raised when audit details contain unsupported or sensitive metadata."""


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize_detail(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DETAIL_DEPTH:
        raise AuditMetadataError("Audit metadata is nested too deeply.")

    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise AuditMetadataError("Audit metadata contains a non-finite number.")
        raise AuditMetadataError("Audit metadata numbers must be integers.")
    if isinstance(value, str):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_LIST_ITEMS:
            raise AuditMetadataError("Audit metadata contains too many items.")
        return [_sanitize_detail(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not _DETAIL_KEY_PATTERN.fullmatch(key):
                raise AuditMetadataError("Audit metadata contains an invalid key.")
            if _is_sensitive_key(key):
                raise AuditMetadataError("Audit metadata contains a sensitive key.")
            sanitized[key] = _sanitize_detail(item, depth=depth + 1)
        return sanitized

    raise AuditMetadataError("Audit metadata contains an unsupported value.")


def sanitize_details(details: dict[str, Any] | None) -> dict[str, Any]:
    sanitized = _sanitize_detail(details or {})
    if not isinstance(sanitized, dict):
        raise AuditMetadataError("Audit details must be an object.")
    if len(canonical_json_bytes(sanitized)) > _MAX_DETAILS_BYTES:
        raise AuditMetadataError("Audit metadata is too large.")
    return sanitized


def _canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_event_payload(
    *,
    chain_index: int,
    event_id: UUID,
    actor_id: UUID | None,
    document_id: UUID | None,
    action: str,
    outcome: str,
    occurred_at: datetime,
    request_id: str | None,
    details: dict[str, Any],
    previous_hash: str | None,
) -> dict[str, Any]:
    return {
        "schema": AUDIT_HASH_SCHEMA,
        "chain_index": chain_index,
        "event_id": str(event_id),
        "actor_id": str(actor_id) if actor_id else None,
        "document_id": str(document_id) if document_id else None,
        "action": action,
        "outcome": outcome,
        "occurred_at": _canonical_datetime(occurred_at),
        "request_id": request_id,
        "details": details,
        "previous_hash": previous_hash,
    }


def calculate_event_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def record_event(
    session: Session,
    *,
    action: AuditAction,
    outcome: AuditOutcome,
    actor: User | None = None,
    document_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one event to the chain within the caller's current transaction."""

    try:
        normalized_details = sanitize_details(details)
        for key, value in get_request_metadata().items():
            normalized_details.setdefault(key, value)
        if actor is not None:
            normalized_details["actor_name"] = actor.name
        if len(canonical_json_bytes(normalized_details)) > _MAX_DETAILS_BYTES:
            raise AuditMetadataError("Audit metadata is too large.")

        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _AUDIT_CHAIN_LOCK_ID},
        )
        previous = session.scalar(
            select(AuditEvent)
            .order_by(AuditEvent.chain_index.desc())
            .limit(1)
        )
        chain_index = 1 if previous is None else previous.chain_index + 1
        previous_hash = previous.event_hash if previous is not None else None
        occurred_at = datetime.now(timezone.utc)
        event_id = uuid4()

        payload = canonical_event_payload(
            chain_index=chain_index,
            event_id=event_id,
            actor_id=actor.id if actor is not None else None,
            document_id=document_id,
            action=action.value,
            outcome=outcome.value,
            occurred_at=occurred_at,
            request_id=get_request_id(),
            details=normalized_details,
            previous_hash=previous_hash,
        )
        event = AuditEvent(
            id=event_id,
            chain_index=chain_index,
            actor_id=actor.id if actor is not None else None,
            document_id=document_id,
            action=action.value,
            outcome=outcome.value,
            occurred_at=occurred_at,
            request_id=get_request_id(),
            details=normalized_details,
            previous_hash=previous_hash,
            event_hash=calculate_event_hash(payload),
        )
        session.add(event)
        session.flush()
        return event
    except Exception as exc:
        logger.error(
            "Mandatory audit event could not be recorded action=%s outcome=%s.",
            action.value,
            outcome.value,
        )
        raise AuditWriteError("The audit event could not be recorded.") from exc


def record_best_effort(
    session: Session,
    *,
    action: AuditAction,
    outcome: AuditOutcome,
    actor: User | None = None,
    document_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent | None:
    """Persist a denial/failure event without changing the original outcome."""

    try:
        event = record_event(
            session,
            action=action,
            outcome=outcome,
            actor=actor,
            document_id=document_id,
            details=details,
        )
        session.commit()
        return event
    except Exception:
        logger.error(
            "Best-effort audit event could not be recorded action=%s outcome=%s.",
            action.value,
            outcome.value,
        )
        try:
            session.rollback()
        except Exception:
            logger.error("Database rollback failed after an audit write error.")
        return None
