from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.api.auth import sync_supabase_session
from app.models.audit_event import AuditEvent
from app.models.enums import AuditAction, AuditOutcome
from app.models.user import User
from app.services.supabase_auth import SupabaseAuthError
from tests.auth_helpers import DEFAULT_PASSWORD, register, unique_email


@pytest.fixture(autouse=True)
def _isolate_provider_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let tests call the real Supabase admin API."""

    monkeypatch.setattr(
        "app.api.auth.find_supabase_user_by_email",
        lambda _email: None,
    )


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
        "app.api.auth.create_supabase_user",
        fake_signup,
    )
    otp_calls = []
    monkeypatch.setattr(
        "app.api.auth.supabase_sign_in_with_otp",
        lambda email, redirect_to: otp_calls.append((email, redirect_to)),
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
    assert otp_calls == [(email, "http://localhost:5173/verify-account")]
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


def test_confirmation_resend_uses_the_configured_redirect_and_is_generic(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_confirmation_resend")
    calls = []
    monkeypatch.setattr(
        "app.api.auth.supabase_sign_in_with_otp",
        lambda requested_email, redirect: calls.append((requested_email, redirect)),
    )

    response = api_client.post(
        "/api/v1/auth/supabase/resend-confirmation",
        json={"email": f" {email.upper()} "},
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "If an account is awaiting confirmation, a new email will be sent."
    }
    assert response.headers["cache-control"] == "no-store"
    assert calls == [(email, "http://localhost:5173/verify-account")]
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.SUCCESS.value,
        )
    )
    assert event is not None
    assert event.actor_id is None
    assert email not in str(event.details)

    blocked = api_client.post(
        "/api/v1/auth/supabase/resend-confirmation",
        json={"email": email},
        headers={"Origin": "http://localhost:5173"},
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert len(calls) == 1


def test_immediate_supabase_signup_creates_normal_profile_and_audits(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_signup_session")
    provider_id = uuid4()
    monkeypatch.setattr(
        "app.api.auth.create_supabase_user",
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
        "app.api.auth.supabase_sign_in_with_otp",
        lambda *_args: None,
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
    # OTP-based signup always requires email confirmation.
    assert response.json() == {
        "account_created": True,
        "requires_email_confirmation": True,
    }
    # No TrustVault profile is created until OTP verification.
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is None
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
    assert DEFAULT_PASSWORD not in str(event.details)
    assert "provider-access-token" not in str(event.details)


def test_duplicate_obfuscated_signup_does_not_claim_account_creation(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_signup_duplicate")
    monkeypatch.setattr(
        "app.api.auth.create_supabase_user",
        lambda *_args: {
            "user": {
                "id": str(uuid4()),
                "email": email,
                "identities": [],
            },
            "session": None,
        },
    )
    monkeypatch.setattr(
        "app.api.auth.supabase_sign_in_with_otp",
        lambda *_args: None,
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
    # OTP-based signup always claims account creation (user created in Supabase Auth).
    assert response.json() == {
        "account_created": True,
        "requires_email_confirmation": True,
    }
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.SUCCESS.value,
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

    monkeypatch.setattr("app.api.auth.create_supabase_user", reject_signup)
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


def test_registration_existing_local_profile_asks_the_user_to_sign_in(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_register_existing_local")
    assert register(api_client, email=email).status_code == 201

    signup_calls = []
    monkeypatch.setattr(
        "app.api.auth.find_supabase_user_by_email",
        lambda requested_email: {
            "id": str(uuid4()),
            "email": requested_email,
            "email_confirmed_at": "2026-01-01T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        "app.api.auth.create_supabase_user",
        lambda *args: signup_calls.append(args),
    )

    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "Existing User",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 400
    assert "already registered" in response.json()["error"]["message"].lower()
    assert signup_calls == []
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.FAILURE.value,
        )
    )
    assert event is not None
    assert event.details["reason"] == "email_already_registered"
    assert email not in str(event.details)


def test_registration_recreates_the_provider_account_for_an_orphaned_profile(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    """A local row with no Supabase identity must not block a fresh signup."""

    email = unique_email("supabase_register_orphaned")
    assert register(api_client, email=email).status_code == 201
    local_user = db_session.scalar(select(User).where(User.email == email))
    assert local_user is not None
    stale_provider_id = uuid4()
    local_user.supabase_auth_id = stale_provider_id
    db_session.commit()

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

    # The autouse fixture already reports "no provider account" for this email.
    monkeypatch.setattr("app.api.auth.create_supabase_user", fake_signup)
    monkeypatch.setattr("app.api.auth.supabase_sign_in_with_otp", lambda *_args: None)

    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "Orphaned User",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "account_created": True,
        "requires_email_confirmation": True,
    }
    assert len(signup_calls) == 1
    db_session.refresh(local_user)
    assert local_user.supabase_auth_id is None
    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.SUCCESS.value,
        )
    ).all()
    assert any(
        event.details.get("request_status") == "confirmation_pending"
        for event in events
    )


def test_registration_fails_closed_when_the_provider_lookup_is_unavailable(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_register_lookup_down")
    assert register(api_client, email=email).status_code == 201

    def unavailable(_email):
        raise SupabaseAuthError(503)

    monkeypatch.setattr("app.api.auth.find_supabase_user_by_email", unavailable)
    monkeypatch.setattr(
        "app.api.auth.create_supabase_user",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("signup must not run while the lookup is unknown")
        ),
    )

    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "Lookup Down",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 503
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.FAILURE.value,
        )
    )
    assert event is not None
    assert event.details["reason"] == "provider_lookup_unavailable"


def test_registration_resends_the_code_for_an_unconfirmed_provider_account(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_register_unconfirmed")
    provider_id = uuid4()
    resend_calls = []

    monkeypatch.setattr(
        "app.api.auth.find_supabase_user_by_email",
        lambda requested_email: {
            "id": str(provider_id),
            "email": requested_email,
            "email_confirmed_at": None,
        },
    )
    monkeypatch.setattr(
        "app.api.auth.supabase_sign_in_with_otp",
        lambda requested_email, redirect: resend_calls.append(
            (requested_email, redirect)
        ),
    )
    monkeypatch.setattr(
        "app.api.auth.create_supabase_user",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("signup must not run for an existing account")
        ),
    )

    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "Pending User",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "account_created": False,
        "requires_email_confirmation": True,
    }
    assert resend_calls == [(email, "http://localhost:5173/verify-account")]
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.SUCCESS.value,
        )
    )
    assert event is not None
    assert event.details["request_status"] == "confirmation_resent"
    assert event.details["provider_user_id"] == str(provider_id)
    assert email not in str(event.details)


def test_registration_rejects_a_confirmed_provider_account(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_register_confirmed")
    signup_calls = []

    monkeypatch.setattr(
        "app.api.auth.find_supabase_user_by_email",
        lambda requested_email: {
            "id": str(uuid4()),
            "email": requested_email,
            "email_confirmed_at": "2026-01-01T00:00:00Z",
        },
    )
    monkeypatch.setattr(
        "app.api.auth.create_supabase_user",
        lambda *args: signup_calls.append(args),
    )

    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "Confirmed User",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 400
    assert "already registered" in response.json()["error"]["message"].lower()
    assert signup_calls == []
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.FAILURE.value,
        )
    )
    assert event is not None
    assert event.details["reason"] == "email_already_registered"


def test_registration_recovers_when_the_provider_reports_an_existing_account(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("supabase_register_provider_race")
    resend_calls = []

    def reject_as_existing(*_args):
        raise SupabaseAuthError(
            400,
            provider_error="User already registered",
        )

    monkeypatch.setattr("app.api.auth.create_supabase_user", reject_as_existing)
    monkeypatch.setattr(
        "app.api.auth.supabase_sign_in_with_otp",
        lambda requested_email, redirect: resend_calls.append(
            (requested_email, redirect)
        ),
    )

    response = api_client.post(
        "/api/v1/auth/supabase/register",
        json={
            "name": "Racing User",
            "email": email,
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "account_created": False,
        "requires_email_confirmation": True,
    }
    assert resend_calls == [(email, "http://localhost:5173/verify-account")]
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.USER_REGISTERED.value,
            AuditEvent.outcome == AuditOutcome.SUCCESS.value,
        )
    )
    assert event is not None
    assert event.details["request_status"] == "confirmation_resent"
