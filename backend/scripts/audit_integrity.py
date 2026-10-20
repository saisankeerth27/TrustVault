"""Verify the audit hash chain or create a signed external checkpoint.

Usage (from backend/):
    python -m scripts.audit_integrity
    python -m scripts.audit_integrity --create-checkpoint

The command never prints the checkpoint signing key. Exit code 0 means the
chain is fully verified, or a new checkpoint was written successfully.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.audit_integrity import (
    CheckpointConfigurationError,
    CheckpointWriteError,
    create_checkpoint,
    verify_audit_trail,
)

_EXIT_VERIFIED = 0
_EXIT_ATTENTION_REQUIRED = 1
_EXIT_CONFIGURATION_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the TrustVault audit chain or write a signed checkpoint."
    )
    parser.add_argument(
        "--create-checkpoint",
        action="store_true",
        help="Write a signed checkpoint covering the current valid chain.",
    )
    return parser


def _print(document: object) -> None:
    print(json.dumps(document, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        session_factory = get_session_factory()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return _EXIT_CONFIGURATION_ERROR

    settings = get_settings()

    with session_factory() as session:
        if args.create_checkpoint:
            try:
                checkpoint = create_checkpoint(session, settings=settings)
            except CheckpointConfigurationError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return _EXIT_CONFIGURATION_ERROR
            except CheckpointWriteError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return _EXIT_ATTENTION_REQUIRED

            _print(
                {
                    "status": "CHECKPOINT_WRITTEN",
                    "checkpoint": checkpoint["payload"],
                }
            )
            return _EXIT_VERIFIED

        verification = verify_audit_trail(session, settings=settings)
        _print(
            {
                "status": verification.status,
                "chain": {
                    "status": verification.chain.status,
                    "event_count": verification.chain.event_count,
                    "last_chain_index": verification.chain.last_chain_index,
                    "last_event_hash": verification.chain.last_event_hash,
                    "failure_chain_index": verification.chain.failure_chain_index,
                    "message": verification.chain.message,
                },
                "checkpoint": {
                    "status": verification.checkpoint.status,
                    "last_chain_index": verification.checkpoint.last_chain_index,
                    "created_at": verification.checkpoint.created_at,
                    "message": verification.checkpoint.message,
                },
            }
        )
        if verification.status == "VERIFIED":
            return _EXIT_VERIFIED
        return _EXIT_ATTENTION_REQUIRED


if __name__ == "__main__":
    raise SystemExit(main())
