from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.models.document_permission import DocumentPermission
from tests.factories import (
    make_audit_event,
    make_document,
    make_document_version,
    make_permission,
    make_user,
)


def test_unique_email_is_enforced(db_session: Session) -> None:
    db_session.add(make_user(email="duplicate@example.com"))
    db_session.flush()

    db_session.add(make_user(email="duplicate@example.com"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_email_must_be_normalized(db_session: Session) -> None:
    db_session.add(make_user(email="Upper@Example.com"))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_document_owner_must_exist(db_session: Session) -> None:
    db_session.add(make_document(owner_id=uuid4()))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_negative_file_size_is_rejected(db_session: Session) -> None:
    owner = make_user()
    db_session.add(owner)
    db_session.flush()

    db_session.add(make_document(owner_id=owner.id, file_size=-1))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_storage_key_cannot_be_a_public_url(db_session: Session) -> None:
    owner = make_user()
    db_session.add(owner)
    db_session.flush()

    db_session.add(
        make_document(owner_id=owner.id, storage_key="https://bucket.example/file.pdf")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_only_read_and_edit_permissions_are_valid(db_session: Session) -> None:
    owner = make_user()
    viewer = make_user()
    db_session.add_all([owner, viewer])
    db_session.flush()

    document = make_document(owner_id=owner.id)
    db_session.add(document)
    db_session.flush()

    db_session.add(
        make_permission(document.id, viewer.id, granted_by=owner.id, permission="ADMIN")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_duplicate_active_permission_is_rejected(db_session: Session) -> None:
    owner = make_user()
    viewer = make_user()
    db_session.add_all([owner, viewer])
    db_session.flush()

    document = make_document(owner_id=owner.id)
    db_session.add(document)
    db_session.flush()

    db_session.add(make_permission(document.id, viewer.id, granted_by=owner.id))
    db_session.flush()

    db_session.add(make_permission(document.id, viewer.id, granted_by=owner.id))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_regranting_after_revocation_preserves_history(db_session: Session) -> None:
    owner = make_user()
    viewer = make_user()
    db_session.add_all([owner, viewer])
    db_session.flush()

    document = make_document(owner_id=owner.id)
    db_session.add(document)
    db_session.flush()

    first_grant = make_permission(document.id, viewer.id, granted_by=owner.id)
    db_session.add(first_grant)
    db_session.flush()

    first_grant.revoked_at = datetime.now(timezone.utc)
    db_session.flush()

    second_grant = make_permission(document.id, viewer.id, granted_by=owner.id)
    db_session.add(second_grant)
    db_session.flush()

    history_count = db_session.scalar(
        select(func.count())
        .select_from(DocumentPermission)
        .where(DocumentPermission.document_id == document.id)
    )
    active_count = db_session.scalar(
        select(func.count())
        .select_from(DocumentPermission)
        .where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.revoked_at.is_(None),
        )
    )

    assert history_count == 2
    assert active_count == 1

    db_session.add(make_permission(document.id, viewer.id, granted_by=owner.id))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize(
    "overrides",
    [
        {"version_number": 0},
        {"original_filename": "   "},
        {"file_size": -1},
        {"storage_key": "https://bucket.example/file.pdf"},
        {"checksum": "not-a-sha256"},
    ],
)
def test_document_version_content_constraints(
    db_session: Session,
    overrides: dict[str, object],
) -> None:
    owner = make_user()
    db_session.add(owner)
    db_session.flush()
    document = make_document(owner_id=owner.id)
    db_session.add(document)
    db_session.flush()

    db_session.add(
        make_document_version(
            document.id,
            uploaded_by=owner.id,
            **overrides,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_document_version_numbers_are_unique_per_document(
    db_session: Session,
) -> None:
    owner = make_user()
    db_session.add(owner)
    db_session.flush()
    document = make_document(owner_id=owner.id)
    db_session.add(document)
    db_session.flush()

    db_session.add(make_document_version(document.id, uploaded_by=owner.id))
    db_session.flush()
    db_session.add(
        make_document_version(
            document.id,
            uploaded_by=owner.id,
            version_number=1,
            is_current=False,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_only_one_current_document_version_is_allowed(
    db_session: Session,
) -> None:
    owner = make_user()
    db_session.add(owner)
    db_session.flush()
    document = make_document(owner_id=owner.id)
    db_session.add(document)
    db_session.flush()

    db_session.add(make_document_version(document.id, uploaded_by=owner.id))
    db_session.flush()
    db_session.add(
        make_document_version(
            document.id,
            uploaded_by=owner.id,
            version_number=2,
            is_current=True,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_version_storage_keys_are_unique_across_documents(
    db_session: Session,
) -> None:
    owner = make_user()
    db_session.add(owner)
    db_session.flush()
    first_document = make_document(owner_id=owner.id)
    second_document = make_document(owner_id=owner.id)
    db_session.add_all([first_document, second_document])
    db_session.flush()

    shared_key = "documents/shared/versions/1.pdf"
    db_session.add(
        make_document_version(
            first_document.id,
            uploaded_by=owner.id,
            storage_key=shared_key,
        )
    )
    db_session.flush()
    db_session.add(
        make_document_version(
            second_document.id,
            uploaded_by=owner.id,
            storage_key=shared_key,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_audit_events_survive_user_and_document_deletion(db_session: Session) -> None:
    owner = make_user()
    viewer = make_user()
    db_session.add_all([owner, viewer])
    db_session.flush()

    document = make_document(owner_id=owner.id)
    db_session.add(document)
    db_session.flush()

    permission = make_permission(document.id, viewer.id, granted_by=owner.id)
    audit = make_audit_event(actor_id=owner.id, document_id=document.id)
    db_session.add_all([permission, audit])
    db_session.flush()

    audit_id = audit.id

    db_session.delete(document)
    db_session.flush()
    db_session.delete(owner)
    db_session.flush()
    db_session.expire_all()

    retained = db_session.get(AuditEvent, audit_id)
    assert retained is not None
    assert retained.action == "DOCUMENT_ACCESS_DENIED"
    assert retained.actor_id is None
    assert retained.document_id is None


def test_audit_event_can_record_denied_attempt_without_actor_or_document(
    db_session: Session,
) -> None:
    event = make_audit_event(action="DOCUMENT_ACCESS_DENIED", outcome="DENIED")
    db_session.add(event)
    db_session.flush()

    assert event.id is not None
    assert event.actor_id is None
    assert event.document_id is None


def test_audit_details_must_be_a_json_object(db_session: Session) -> None:
    event = make_audit_event(details=["not", "an", "object"])  # type: ignore[arg-type]
    db_session.add(event)

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_audit_hash_format_is_validated(db_session: Session) -> None:
    db_session.add(make_audit_event(event_hash="too-short"))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
