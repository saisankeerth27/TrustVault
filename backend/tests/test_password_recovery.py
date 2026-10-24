from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.audit_event import AuditEvent
from app.models.enums import AuditAction, AuditOutcome
from app.models.user import User
from app.services.supabase_auth import SupabaseAuthError
from tests.auth_helpers import DEFAULT_PASSWORD, register, unique_email


def _provider_failure(status_code: int) -> Callable[..., None]:
    def fail(*_args):
        raise SupabaseAuthError(status_code)

    return fail


def test_recovery_request_is_generic_and_does_not_audit_email(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("recovery_request")
    calls = []
    monkeypatch.setattr(
        "app.api.auth.request_password_recovery",
        lambda requested_email, redirect: calls.append((requested_email, redirect)),
    )

    response = api_client.post(
        "/api/v1/auth/recovery/request",
        json={"email": f" {email.upper()} "},
    )

    assert response.status_code == 200
    assert response.json()["message"] == (
        "If an account exists for this email address, a verification code will be sent."
    )
    assert calls[0][0] == email
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.PASSWORD_RESET_REQUESTED.value
        )
    )
    assert event is not None
    assert event.outcome == AuditOutcome.SUCCESS.value
    assert event.actor_id is None
    assert email not in str(event.details)


def test_recovery_request_provider_failure_returns_safe_error_and_audits_failure(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("recovery_provider_failure")
    monkeypatch.setattr(
        "app.api.auth.request_password_recovery",
        _provider_failure(500),
    )

    response = api_client.post(
        "/api/v1/auth/recovery/request",
        json={"email": email},
    )

    assert response.status_code == 503
    assert email not in response.text
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.PASSWORD_RESET_REQUEST_FAILED.value
        )
    )
    assert event is not None
    assert event.outcome == AuditOutcome.FAILURE.value
    assert event.actor_id is None


def test_recovery_request_reports_missing_backend_configuration(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    def missing_configuration(*_args):
        raise SupabaseAuthError(configuration_missing=True)

    monkeypatch.setattr(
        "app.api.auth.request_password_recovery",
        missing_configuration,
    )

    response = api_client.post(
        "/api/v1/auth/recovery/request",
        json={"email": unique_email("recovery_missing_config")},
    )

    assert response.status_code == 503
    assert "SUPABASE_URL" in response.json()["error"]["message"]
    assert "SUPABASE_ANON_KEY" in response.json()["error"]["message"]
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.PASSWORD_RESET_REQUEST_FAILED.value
        )
    )
    assert event is not None
    assert event.details["reason"] == "missing_configuration"


def test_recovery_request_rate_limit_is_enforced(
    api_client: TestClient,
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        "app.api.auth.request_password_recovery",
        lambda *args: calls.append(args),
    )
    email = unique_email("recovery_rate_limit")

    responses = [
        api_client.post("/api/v1/auth/recovery/request", json={"email": email})
        for _ in range(4)
    ]

    assert [response.status_code for response in responses] == [200, 200, 200, 429]
    assert responses[-1].headers["retry-after"] == "900"
    assert len(calls) == 3


def test_recovery_request_rejects_untrusted_origin(
    api_client: TestClient,
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        "app.api.auth.request_password_recovery",
        lambda *args: calls.append(args),
    )

    response = api_client.post(
        "/api/v1/auth/recovery/request",
        json={"email": unique_email("recovery_origin")},
        headers={
            "Origin": "https://attacker.example",
            "Sec-Fetch-Site": "cross-site",
        },
    )

    assert response.status_code == 403
    assert calls == []


def test_recovery_verification_requires_recovery_otp_and_uses_http_only_cookie(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("recovery_verify")
    registration = register(api_client, email=email)
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    calls = []

    def verify(requested_email, token):
        calls.append((requested_email, token))
        return {
            "access_token": "provider-recovery-access-token",
            "user": {"id": str(user.id), "email": email},
        }

    monkeypatch.setattr("app.api.auth.verify_recovery_otp", verify)
    response = api_client.post(
        "/api/v1/auth/recovery/verify",
        json={"email": email, "token": "012345"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Email verified. You can now create a new password."
    }
    assert "provider-recovery-access-token" not in response.text
    cookie = response.headers["set-cookie"]
    assert "trustvault_recovery=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=600" in cookie
    assert calls == [(email, "012345")]
    assert registration.status_code == 201

    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action
            == AuditAction.PASSWORD_RESET_VERIFICATION_SUCCEEDED.value
        )
    )
    assert event is not None
    assert event.actor_id == user.id
    assert event.details["target_user_id"] == str(user.id)
    assert "012345" not in str(event.details)


def test_invalid_recovery_code_does_not_issue_cookie_or_update_password(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    def reject_code(_email, _token):
        raise SupabaseAuthError(422)

    monkeypatch.setattr("app.api.auth.verify_recovery_otp", reject_code)
    response = api_client.post(
        "/api/v1/auth/recovery/verify",
        json={"email": unique_email("recovery_invalid"), "token": "111111"},
    )
    update_response = api_client.post(
        "/api/v1/auth/recovery/update-password",
        json={"password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 400
    assert "set-cookie" not in response.headers
    assert update_response.status_code == 401
    assert "trustvault_recovery=" in update_response.headers["set-cookie"]
    assert "Max-Age=0" in update_response.headers["set-cookie"]
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action
            == AuditAction.PASSWORD_RESET_VERIFICATION_FAILED.value
        )
    )
    assert event is not None
    assert event.actor_id is None
    assert "111111" not in str(event.details)


def test_verified_recovery_updates_supabase_and_audits_password_changed(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("recovery_update")
    register(api_client, email=email)
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    monkeypatch.setattr(
        "app.api.auth.verify_recovery_otp",
        lambda _email, _token: {
            "access_token": "recovery-session",
            "user": {"id": str(user.id), "email": email},
        },
    )
    monkeypatch.setattr(
        "app.api.auth.get_supabase_user",
        lambda _token: {
            "id": str(user.id),
            "email": email,
            "email_confirmed_at": "verified",
        },
    )
    updates = []
    monkeypatch.setattr(
        "app.api.auth.update_recovery_password",
        lambda token, password: updates.append((token, password)),
    )

    verify_response = api_client.post(
        "/api/v1/auth/recovery/verify",
        json={"email": email, "token": "123456"},
    )
    update_response = api_client.post(
        "/api/v1/auth/recovery/update-password",
        json={"password": "A new long secure password 123!"},
    )

    assert verify_response.status_code == 200
    assert update_response.status_code == 200
    assert updates == [
        ("recovery-session", "A new long secure password 123!")
    ]
    assert "trustvault_recovery=" in update_response.headers["set-cookie"]
    assert "Max-Age=0" in update_response.headers["set-cookie"]
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.PASSWORD_CHANGED.value
        )
    )
    assert event is not None
    assert event.actor_id == user.id
    assert event.outcome == AuditOutcome.SUCCESS.value
    assert "A new long secure password 123!" not in str(event.details)


def test_password_update_audit_failure_reports_partial_success_and_clears_cookie(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("recovery_audit_failure")
    register(api_client, email=email)
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    monkeypatch.setattr(
        "app.api.auth.verify_recovery_otp",
        lambda _email, _token: {
            "access_token": "recovery-session",
            "user": {"id": str(user.id), "email": email},
        },
    )
    monkeypatch.setattr(
        "app.api.auth.get_supabase_user",
        lambda _token: {"id": str(user.id), "email": email},
    )
    updates = []
    monkeypatch.setattr(
        "app.api.auth.update_recovery_password",
        lambda token, password: updates.append((token, password)),
    )
    verify_response = api_client.post(
        "/api/v1/auth/recovery/verify",
        json={"email": email, "token": "123456"},
    )
    assert verify_response.status_code == 200

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit database unavailable")

    monkeypatch.setattr("app.api.auth.record_event", fail_audit)
    response = api_client.post(
        "/api/v1/auth/recovery/update-password",
        json={"password": "A new long secure password 789!"},
    )

    assert response.status_code == 500
    assert (
        "Supabase confirmed the password update"
        in response.json()["error"]["message"]
    )
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    assert updates == [("recovery-session", "A new long secure password 789!")]
    assert db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.PASSWORD_CHANGED.value
        )
    ) is None


def test_expired_recovery_cookie_is_cleared(
    api_client: TestClient,
    monkeypatch,
) -> None:
    email = unique_email("recovery_expired")
    monkeypatch.setattr(
        "app.api.auth.verify_recovery_otp",
        lambda _email, _token: {
            "access_token": "expired-recovery-session",
            "user": {
                "id": "d96f6c9c-98c7-4f5b-9c77-0df0b4ee0001",
                "email": email,
            },
        },
    )
    monkeypatch.setattr(
        "app.api.auth.get_supabase_user",
        _provider_failure(401),
    )

    verify_response = api_client.post(
        "/api/v1/auth/recovery/verify",
        json={"email": email, "token": "123456"},
    )
    update_response = api_client.post(
        "/api/v1/auth/recovery/update-password",
        json={"password": "A new long secure password 123!"},
    )

    assert verify_response.status_code == 200
    assert update_response.status_code == 401
    assert "trustvault_recovery=" in update_response.headers["set-cookie"]
    assert "Max-Age=0" in update_response.headers["set-cookie"]


def test_password_update_provider_failure_is_audited_without_password(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    email = unique_email("recovery_update_failure")
    register(api_client, email=email)
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    monkeypatch.setattr(
        "app.api.auth.verify_recovery_otp",
        lambda _email, _token: {
            "access_token": "recovery-session",
            "user": {"id": str(user.id), "email": email},
        },
    )
    monkeypatch.setattr(
        "app.api.auth.get_supabase_user",
        lambda _token: {
            "id": str(user.id),
            "email": email,
            "email_confirmed_at": "verified",
        },
    )
    monkeypatch.setattr(
        "app.api.auth.update_recovery_password",
        _provider_failure(422),
    )
    new_password = "A different secure password 456!"

    api_client.post(
        "/api/v1/auth/recovery/verify",
        json={"email": email, "token": "123456"},
    )
    response = api_client.post(
        "/api/v1/auth/recovery/update-password",
        json={"password": new_password},
    )

    assert response.status_code == 400
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.PASSWORD_UPDATE_FAILED.value
        )
    )
    assert event is not None
    assert event.actor_id == user.id
    assert event.outcome == AuditOutcome.FAILURE.value
    assert new_password not in str(event.details)
