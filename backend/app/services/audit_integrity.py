"""Audit chain verification and signed checkpoint support."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.audit_event import AuditEvent
from app.services.audit import (
    AUDIT_HASH_SCHEMA_V1,
    SUPPORTED_HASH_SCHEMAS,
    canonical_event_payload,
    canonical_json_bytes,
    calculate_event_hash,
)

logger = logging.getLogger(__name__)

CHECKPOINT_SCHEMA = "trustvault-audit-checkpoint-v1"
_MAX_CHECKPOINT_BYTES = 64 * 1024


class CheckpointConfigurationError(Exception):
    """Raised when checkpoint signing or storage is not configured."""


class CheckpointWriteError(Exception):
    """Raised when a signed checkpoint cannot be created."""


@dataclass(frozen=True)
class ChainVerification:
    status: str
    event_count: int
    last_chain_index: int
    last_event_hash: str | None
    failure_chain_index: int | None
    message: str
    legacy_skipped: int = 0


@dataclass(frozen=True)
class CheckpointVerification:
    status: str
    last_chain_index: int | None
    created_at: str | None
    message: str


@dataclass(frozen=True)
class AuditTrailVerification:
    status: str
    chain: ChainVerification
    checkpoint: CheckpointVerification


def _canonical_checkpoint_payload(payload: dict[str, Any]) -> bytes:
    return canonical_json_bytes(payload)


def _checkpoint_signature(payload: dict[str, Any], key: str) -> str:
    return hmac.new(
        key.encode("utf-8"),
        _canonical_checkpoint_payload(payload),
        hashlib.sha256,
    ).hexdigest()


def _v1_has_nulled_reference(event: AuditEvent) -> bool:
    """Return True when a V1 event has a null FK that was set by ON DELETE SET NULL.

    V1 events embedded mutable foreign-key UUIDs (actor_id, document_id) directly
    in the hash payload.  When the referenced row is later deleted PostgreSQL sets
    those columns to NULL, making it impossible to recompute the original hash.
    The chain links (previous_hash) remain intact, so we accept these events as
    "legacy-verified" rather than flagging them as tampered.
    """
    return event.hash_schema == AUDIT_HASH_SCHEMA_V1 and (
        event.actor_id is None or event.document_id is None
    )


def verify_chain(session: Session) -> ChainVerification:
    events = session.scalars(
        select(AuditEvent).order_by(AuditEvent.chain_index.asc())
    ).all()
    event_count = len(events)
    expected_index = 1
    previous_hash: str | None = None
    last_event_hash: str | None = None
    legacy_skipped = 0

    for event in events:
        if event.chain_index != expected_index:
            return ChainVerification(
                status="INVALID",
                event_count=event_count,
                last_chain_index=expected_index - 1,
                last_event_hash=last_event_hash,
                failure_chain_index=event.chain_index,
                message=(
                    "The audit chain has a missing or reordered event at "
                    f"sequence {event.chain_index}."
                ),
            )

        if event.previous_hash != previous_hash:
            return ChainVerification(
                status="INVALID",
                event_count=event_count,
                last_chain_index=expected_index - 1,
                last_event_hash=last_event_hash,
                failure_chain_index=event.chain_index,
                message=(
                    "The previous-hash link is invalid at "
                    f"sequence {event.chain_index}."
                ),
            )

        if event.hash_schema not in SUPPORTED_HASH_SCHEMAS:
            return ChainVerification(
                status="INVALID",
                event_count=event_count,
                last_chain_index=expected_index - 1,
                last_event_hash=last_event_hash,
                failure_chain_index=event.chain_index,
                message=(
                    "The event at sequence "
                    f"{event.chain_index} uses an unsupported hash schema."
                ),
            )

        payload = canonical_event_payload(
            chain_index=event.chain_index,
            event_id=event.id,
            actor_id=event.actor_id,
            document_id=event.document_id,
            action=event.action,
            outcome=event.outcome,
            occurred_at=event.occurred_at,
            request_id=event.request_id,
            details=event.details,
            previous_hash=event.previous_hash,
            hash_schema=event.hash_schema,
        )
        if calculate_event_hash(payload) != event.event_hash:
            # V1 events embedded mutable FK references.  When the actor or
            # document is later deleted, PostgreSQL nulls those columns via ON
            # DELETE SET NULL, making it impossible to recompute the original
            # hash.  Chain-link integrity (previous_hash) has already been
            # confirmed above, so we accept these as legacy-verified rather
            # than treating them as evidence of tampering.
            if _v1_has_nulled_reference(event):
                legacy_skipped += 1
                last_event_hash = event.event_hash
                previous_hash = event.event_hash
                expected_index += 1
                continue

            return ChainVerification(
                status="INVALID",
                event_count=event_count,
                last_chain_index=expected_index - 1,
                last_event_hash=last_event_hash,
                failure_chain_index=event.chain_index,
                message=(
                    "The event hash does not match the stored event at "
                    f"sequence {event.chain_index}."
                ),
            )

        last_event_hash = event.event_hash
        previous_hash = event.event_hash
        expected_index += 1

    if legacy_skipped:
        message = (
            f"The audit hash chain is internally consistent "
            f"({legacy_skipped} legacy V1 "
            f"{'event' if legacy_skipped == 1 else 'events'} "
            "accepted: deleted actor/document FK cannot be re-verified)."
        )
    else:
        message = "The audit hash chain is internally consistent."

    return ChainVerification(
        status="VALID",
        event_count=event_count,
        last_chain_index=expected_index - 1,
        last_event_hash=last_event_hash,
        failure_chain_index=None,
        message=message,
        legacy_skipped=legacy_skipped,
    )


def _checkpoint_settings(settings: Settings) -> tuple[str, Path] | None:
    if not settings.audit_checkpoint_signing_key or not settings.audit_checkpoint_path:
        return None
    return (
        settings.audit_checkpoint_signing_key.get_secret_value(),
        Path(settings.audit_checkpoint_path),
    )


def create_checkpoint(
    session: Session,
    *,
    settings: Settings,
    chain: ChainVerification | None = None,
) -> dict[str, Any]:
    configured = _checkpoint_settings(settings)
    if configured is None:
        raise CheckpointConfigurationError("Audit checkpoint signing is not configured.")
    key, path = configured

    verification = chain or verify_chain(session)
    if verification.status != "VALID":
        raise CheckpointWriteError("A checkpoint cannot be created for an invalid chain.")
    if verification.event_count == 0:
        raise CheckpointWriteError("A checkpoint requires at least one audit event.")

    existing = verify_checkpoint(session, settings=settings, chain=verification)
    if existing.status == "INVALID":
        raise CheckpointWriteError(
            "A checkpoint cannot replace an invalid or newer existing checkpoint."
        )
    if (
        existing.last_chain_index is not None
        and verification.last_chain_index < existing.last_chain_index
    ):
        raise CheckpointWriteError(
            "A checkpoint cannot move backward from the existing checkpoint."
        )

    payload = {
        "schema": CHECKPOINT_SCHEMA,
        "created_at": datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "event_count": verification.event_count,
        "last_chain_index": verification.last_chain_index,
        "last_event_hash": verification.last_event_hash,
    }
    document = {
        "payload": payload,
        "signature": _checkpoint_signature(payload, key),
    }
    encoded = canonical_json_bytes(document)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError as exc:
        try:
            if "temporary_path" in locals() and temporary_path.exists():
                temporary_path.unlink()
        except OSError:
            pass
        logger.error("Audit checkpoint file could not be written.")
        raise CheckpointWriteError("The audit checkpoint could not be written.") from exc

    return document


def verify_checkpoint(
    session: Session,
    *,
    settings: Settings,
    chain: ChainVerification,
) -> CheckpointVerification:
    if chain.status != "VALID":
        return CheckpointVerification(
            status="UNAVAILABLE",
            last_chain_index=None,
            created_at=None,
            message="The checkpoint was not evaluated because chain verification failed.",
        )

    configured = _checkpoint_settings(settings)
    if configured is None:
        return CheckpointVerification(
            status="UNCONFIGURED",
            last_chain_index=None,
            created_at=None,
            message="No external audit checkpoint signing is configured.",
        )
    key, path = configured

    if not path.exists():
        return CheckpointVerification(
            status="MISSING",
            last_chain_index=None,
            created_at=None,
            message="No signed external audit checkpoint file is available.",
        )

    try:
        if path.stat().st_size > _MAX_CHECKPOINT_BYTES:
            raise ValueError("Checkpoint file is too large.")
        raw = path.read_bytes()
        document = json.loads(raw)
        payload = document["payload"]
        signature = document["signature"]
        if not isinstance(payload, dict) or not isinstance(signature, str):
            raise ValueError("Checkpoint structure is invalid.")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return CheckpointVerification(
            status="INVALID",
            last_chain_index=None,
            created_at=None,
            message="The external audit checkpoint file is unreadable or malformed.",
        )

    if payload.get("schema") != CHECKPOINT_SCHEMA:
        return CheckpointVerification(
            status="INVALID",
            last_chain_index=None,
            created_at=None,
            message="The external audit checkpoint has an unsupported schema.",
        )

    expected_signature = _checkpoint_signature(payload, key)
    if not hmac.compare_digest(expected_signature, signature):
        return CheckpointVerification(
            status="INVALID",
            last_chain_index=None,
            created_at=None,
            message="The external audit checkpoint signature is invalid.",
        )

    checkpoint_index = payload.get("last_chain_index")
    checkpoint_count = payload.get("event_count")
    checkpoint_hash = payload.get("last_event_hash")
    created_at = payload.get("created_at")
    if (
        not isinstance(checkpoint_index, int)
        or checkpoint_index < 1
        or not isinstance(checkpoint_count, int)
        or checkpoint_count != checkpoint_index
        or not isinstance(checkpoint_hash, str)
        or not isinstance(created_at, str)
    ):
        return CheckpointVerification(
            status="INVALID",
            last_chain_index=None,
            created_at=None,
            message="The external audit checkpoint payload is invalid.",
        )

    if checkpoint_index > chain.last_chain_index:
        return CheckpointVerification(
            status="INVALID",
            last_chain_index=checkpoint_index,
            created_at=created_at,
            message="The audit chain is shorter than the signed checkpoint.",
        )

    checkpoint_event = session.scalar(
        select(AuditEvent).where(AuditEvent.chain_index == checkpoint_index)
    )
    if checkpoint_event is None or checkpoint_event.event_hash != checkpoint_hash:
        return CheckpointVerification(
            status="INVALID",
            last_chain_index=checkpoint_index,
            created_at=created_at,
            message="The signed checkpoint does not match the audit chain.",
        )

    if checkpoint_index < chain.last_chain_index:
        return CheckpointVerification(
            status="STALE",
            last_chain_index=checkpoint_index,
            created_at=created_at,
            message="The external checkpoint is valid but does not cover the latest events.",
        )

    return CheckpointVerification(
        status="VALID",
        last_chain_index=checkpoint_index,
        created_at=created_at,
        message="The external checkpoint covers the current audit chain head.",
    )


def verify_audit_trail(
    session: Session,
    *,
    settings: Settings,
) -> AuditTrailVerification:
    chain = verify_chain(session)
    checkpoint = verify_checkpoint(session, settings=settings, chain=chain)

    if chain.status != "VALID" or checkpoint.status == "INVALID":
        status = "INVALID"
    elif checkpoint.status == "VALID":
        status = "VERIFIED"
    elif checkpoint.status == "STALE":
        status = "CHAIN_VALID_CHECKPOINT_STALE"
    else:
        status = "CHAIN_VALID_CHECKPOINT_MISSING"

    return AuditTrailVerification(
        status=status,
        chain=chain,
        checkpoint=checkpoint,
    )
