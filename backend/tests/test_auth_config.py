from __future__ import annotations

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.auth import _set_refresh_cookie
from app.core.config import Settings, get_settings
from app.main import app


def test_production_does_not_require_legacy_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_COOKIE_SAMESITE", "none")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv(
        "PASSWORD_RECOVERY_REDIRECT_URL",
        "https://app.example.com/recover-password",
    )
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    settings = Settings(_env_file=None)
    assert settings.jwt_secret is None


def test_same_site_none_requires_secure_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("AUTH_COOKIE_SAMESITE", "none")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_cookie_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_COOKIE_SAMESITE", "none")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv(
        "PASSWORD_RECOVERY_REDIRECT_URL",
        "https://app.example.com/recover-password",
    )
    monkeypatch.setenv(
        "EMAIL_CONFIRMATION_REDIRECT_URL",
        "https://app.example.com/verify-account",
    )
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    monkeypatch.setenv(
        "JWT_SECRET", "production-test-secret-with-at-least-32-characters"
    )
    get_settings.cache_clear()

    response = Response()
    _set_refresh_cookie(response, "opaque-refresh-token")
    cookie = response.headers["set-cookie"]

    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=none" in cookie
    assert "Path=/api/v1/auth" in cookie


def test_credentialed_cors_only_for_configured_origins() -> None:
    trusted = TestClient(app).options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert trusted.status_code == 200
    assert trusted.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert trusted.headers["access-control-allow-credentials"] == "true"

    untrusted = TestClient(app).options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in untrusted.headers
