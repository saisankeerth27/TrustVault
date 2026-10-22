"""Shared safe audit event serialization."""

from __future__ import annotations

from app.models.audit_event import AuditEvent
from app.schemas.audit import AuditEventResponse


def audit_event_response(event: AuditEvent) -> AuditEventResponse:
    actor_name = event.actor.name if event.actor is not None else None
    if actor_name is None:
        stored_actor_name = event.details.get("actor_name")
        actor_name = stored_actor_name if isinstance(stored_actor_name, str) else None

    target_user_id = event.details.get("target_user_id")
    if not isinstance(target_user_id, str):
        target_user_id = None
    resource_type = event.details.get("resource_type")

    return AuditEventResponse(
        id=event.id,
        chain_index=event.chain_index,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        actor_name=actor_name,
        document_id=event.document_id,
        document_name=event.document.name if event.document is not None else None,
        target_user_id=target_user_id,
        resource_type=resource_type if isinstance(resource_type, str) else None,
        action=event.action,
        outcome=event.outcome,
        request_id=event.request_id,
        hash_schema=event.hash_schema,
        details=event.details,
    )
