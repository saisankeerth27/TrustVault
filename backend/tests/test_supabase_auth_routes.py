from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.api.auth import sync_supabase_session
from app.models.audit_event import AuditEvent
from app.models.enums import AuditAction, AuditOutcome
from app.models.user import User
from app.services.supabase_auth import SupabaseAuthError
from tests.auth_helpers import DEFAULT_PASSWORD, register, unique_email


def test_supabase_login_records_verified_success(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_login")
    assert register(api_client, email=email).status_code == 201
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    provider_id = uuid4()
    user.supabase_auth_id = provider_id
    db_session.commit()
    monkeypatch.setattr(
        "app.api.auth.sign_in_with_password",
        lambda _email, _password: {
            "access_token": "provider-access-token",
            "refresh_token": "provider-refresh-token",
        },
    )
    monkeypatch.setattr(
        "app.api.auth.get_supabase_user",
        lambda _token: {
            "id": str(provider_id),
            "email": email,
            "email_confirmed_at": "verified",
        },
    )

    response = api_client.post(
        "/api/v1/auth/supabase/login",
        json={"email": email, "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(user.id)
    assert response.json()["session"] == {
        "access_token": "provider-access-token",
        "refresh_token": "provider-refresh-token",
    }
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.LOGIN_SUCCESS.value
        )
    )
    assert event is not None
    assert event.actor_id == user.id
    assert event.outcome == AuditOutcome.SUCCESS.value
    assert "provider-access-token" not in str(event.details)
    assert DEFAULT_PASSWORD not in str(event.details)


def test_supabase_login_failure_is_audited_without_email_or_password(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_login_failure")

    def reject_login(_email, _password):
        raise SupabaseAuthError(400)

    monkeypatch.setattr("app.api.auth.sign_in_with_password", reject_login)
    response = api_client.post(
        "/api/v1/auth/supabase/login",
        json={"email": email, "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.LOGIN_FAILURE.value
        )
    )
    assert event is not None
    assert event.actor_id is None
    assert event.outcome == AuditOutcome.FAILURE.value
    assert email not in str(event.details)
    assert DEFAULT_PASSWORD not in str(event.details)


def test_confirmation_pending_signup_is_audited_without_claiming_delivery(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_signup_pending")
    provider_id = uuid4()
    signup_calls = []

    def fake_signup(*args):
        signup_calls.append(args)
        return {
            "user": {
                "id": str(provider_id),
                "email": email,
                "identities": [{"identity_id": str(provider_id)}],
            },
            "session": None,
        }

    monkeypatch.setattr(
        "app.api.auth.supabase_sign_up",
        fake_signup,
    )

    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "Pending User",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "account_created": True,
        "requires_email_confirmation": True,
    }
    assert signup_calls[0][3] == "http://localhost:5173/login"
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.SUCCESS.value,
        )
    )
    assert event is not None
    assert event.actor_id is None
    assert event.details["provider_user_id"] == str(provider_id)
    assert event.details["request_status"] == "confirmation_pending"
    assert email not in str(event.details)

    profile = sync_supabase_session(
        identity={
            "id": str(provider_id),
            "email": email,
            "email_confirmed_at": "verified",
            "user_metadata": {"name": "Pending User"},
        },
        session=db_session,
    )
    registered_events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.SUCCESS.value,
        )
    ).all()
    assert profile.role.value == "USER"
    assert len(registered_events) == 1


def test_immediate_supabase_signup_creates_normal_profile_and_audits(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_signup_session")
    provider_id = uuid4()
    monkeypatch.setattr(
        "app.api.auth.supabase_sign_up",
        lambda *_args: {
            "access_token": "provider-access-token",
            "refresh_token": "provider-refresh-token",
            "user": {
                "id": str(provider_id),
                "email": email,
                "user_metadata": {"name": "New User"},
            },
        },
    )
    monkeypatch.setattr(
        "app.api.auth.get_supabase_user",
        lambda _token: {
            "id": str(provider_id),
            "email": email,
            "email_confirmed_at": "verified",
            "user_metadata": {"name": "New User"},
        },
    )

    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "New User",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["session"] == {
        "access_token": "provider-access-token",
        "refresh_token": "provider-refresh-token",
    }
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.supabase_auth_id == provider_id
    assert user.role == "USER"
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.SUCCESS.value,
        )
    )
    assert event is not None
    assert event.actor_id == user.id
    assert DEFAULT_PASSWORD not in str(event.details)
    assert "provider-access-token" not in str(event.details)


def test_duplicate_obfuscated_signup_does_not_claim_account_creation(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_signup_duplicate")
    monkeypatch.setattr(
        "app.api.auth.supabase_sign_up",
        lambda *_args: {
            "user": {
                "id": str(uuid4()),
                "email": email,
                "identities": [],
            },
            "session": None,
        },
    )

    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "Duplicate User",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "account_created": False,
        "requires_email_confirmation": True,
    }
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.FAILURE.value,
        )
    )
    assert event is not None
    assert event.actor_id is None
    assert email not in str(event.details)


def test_supabase_signup_failure_is_audited_without_submitted_credentials(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_signup_failure")

    def reject_signup(*_args):
        raise SupabaseAuthError(400)

    monkeypatch.setattr("app.api.auth.supabase_sign_up", reject_signup)
    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "Failed User",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 400
    assert email not in response.text
    assert DEFAULT_PASSWORD not in response.text
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.FAILURE.value,
        )
    )
    assert event is not None
    assert event.actor_id is None
    assert email not in str(event.details)
    assert DEFAULT_PASSWORD not in str(event.details)
