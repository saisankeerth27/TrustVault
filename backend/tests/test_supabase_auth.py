from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.services.supabase_auth import (
    SupabaseAuthError,
    request_password_recovery,
    sign_in_with_password,
    sign_up,
    update_recovery_password,
    verify_recovery_otp,
)


def test_recovery_uses_supabase_auth_recovery_type_and_never_returns_tokens(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    get_settings.cache_clear()
    requests = []

    def fake_request(method, url, **kwargs):
        requests.append((method, url, kwargs))
        return httpx.Response(200, json={"access_token": "recovery-session"})

    monkeypatch.setattr("app.services.supabase_auth.httpx.request", fake_request)
    try:
        request_password_recovery(
            "person@example.com",
            "https://app.example.com/recover-password",
        )
        result = verify_recovery_otp("person@example.com", "123456")
        update_recovery_password("recovery-session", "new password")
    finally:
        get_settings.cache_clear()

    assert requests[0][0:2] == (
        "POST",
        "https://example.supabase.co/auth/v1/recover",
    )
    assert requests[0][2]["json"] == {"email": "person@example.com"}
    assert requests[0][2]["params"] == {
        "redirect_to": "https://app.example.com/recover-password"
    }
    assert requests[1][0:2] == (
        "POST",
        "https://example.supabase.co/auth/v1/verify",
    )
    assert requests[1][2]["json"] == {
        "email": "person@example.com",
        "token": "123456",
        "type": "recovery",
    }
    assert requests[2][0:2] == (
        "PUT",
        "https://example.supabase.co/auth/v1/user",
    )
    assert requests[2][2]["json"] == {"password": "new password"}
    assert result["access_token"] == "recovery-session"


def test_missing_supabase_configuration_fails_without_provider_request(monkeypatch) -> None:
    class MissingConfiguration:
        def require_supabase_auth(self) -> None:
            raise RuntimeError("Supabase Auth is not configured.")

    monkeypatch.setattr(
        "app.services.supabase_auth.get_settings",
        lambda: MissingConfiguration(),
    )

    try:
        verify_recovery_otp("person@example.com", "123456")
    except SupabaseAuthError as exc:
        assert exc.status_code is None
        assert exc.configuration_missing
    else:
        raise AssertionError("Missing Supabase configuration must fail closed.")


def test_supabase_signup_and_password_login_use_public_auth_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    get_settings.cache_clear()
    requests = []

    def fake_request(method, url, **kwargs):
        requests.append((method, url, kwargs))
        return httpx.Response(200, json={"access_token": "provider-access-token"})

    monkeypatch.setattr("app.services.supabase_auth.httpx.request", fake_request)
    try:
        sign_up(
            "person@example.com",
            "secure password",
            "Test Person",
            "http://localhost:5173/login",
        )
        sign_in_with_password("person@example.com", "secure password")
    finally:
        get_settings.cache_clear()

    assert requests[0][0:2] == (
        "POST",
        "https://example.supabase.co/auth/v1/signup",
    )
    assert requests[0][2]["json"] == {
        "email": "person@example.com",
        "password": "secure password",
        "data": {"name": "Test Person"},
    }
    assert requests[0][2]["params"] == {
        "redirect_to": "http://localhost:5173/login"
    }
    assert requests[1][0:2] == (
        "POST",
        "https://example.supabase.co/auth/v1/token",
    )
    assert requests[1][2]["json"] == {
        "email": "person@example.com",
        "password": "secure password",
    }
    assert requests[1][2]["params"] == {"grant_type": "password"}
