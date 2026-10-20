from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_refresh_token, verify_password
from app.models.enums import UserStatus
from app.models.refresh_token import RefreshToken
from app.models.user import User
from tests.auth_helpers import (
    DEFAULT_PASSWORD,
    bearer,
    get_refresh_cookie,
    login,
    register,
    set_refresh_cookie,
    unique_email,
)

USER_FIELDS = {"id", "name", "email", "role", "status", "created_at"}


def _user_by_email(session: Session, email: str) -> User:
    session.expire_all()
    user = session.scalar(select(User).where(User.email == email.lower()))
    assert user is not None
    return user


def test_registration_creates_viewer_and_secure_session(
    api_client: TestClient, db_session: Session
) -> None:
    email = unique_email("register")
    response = register(api_client, email=email)

    assert response.status_code == 201
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 900
    assert payload["user"]["email"] == email.lower()
    assert payload["user"]["role"] == "VIEWER"
    assert payload["user"]["status"] == "ACTIVE"
    assert set(payload["user"]) == USER_FIELDS
    assert "password" not in payload
    assert response.headers["cache-control"] == "no-store"

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("trustvault_refresh=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/v1/auth" in cookie
    assert "Secure" not in cookie

    user = _user_by_email(db_session, email)
    assert user.password_hash != DEFAULT_PASSWORD
    assert verify_password(DEFAULT_PASSWORD, user.password_hash)

    plaintext = get_refresh_cookie(api_client)
    assert plaintext
    stored = db_session.scalar(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    )
    assert stored is not None
    assert stored.token_hash == hash_refresh_token(plaintext)
    assert plaintext not in stored.token_hash

    me = api_client.get(
        "/api/v1/auth/me", headers=bearer(payload["access_token"])
    )
    assert me.status_code == 200
    assert me.json()["id"] == payload["user"]["id"]
    assert me.json()["email"] == email.lower()


def test_registration_normalizes_email_and_rejects_role_injection(
    api_client: TestClient, db_session: Session
) -> None:
    email = "Mixed.Case@Example.COM"
    response = register(api_client, email=email)

    assert response.status_code == 201
    assert response.json()["user"]["email"] == email.lower()
    assert _user_by_email(db_session, email).role == "VIEWER"

    injected = api_client.post(
        "/api/v1/auth/register",
        json={
            "name": "Escalation Attempt",
            "email": unique_email("inject"),
            "password": DEFAULT_PASSWORD,
            "role": "ADMINISTRATOR",
        },
    )
    assert injected.status_code == 422


def test_duplicate_email_is_case_insensitive_conflict(
    api_client: TestClient,
) -> None:
    email = unique_email("duplicate")
    assert register(api_client, email=email).status_code == 201

    duplicate = register(api_client, email=email.upper())
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize("password", ["short-pass1", "a" * 73])
def test_registration_rejects_weak_password_lengths(
    api_client: TestClient, password: str
) -> None:
    response = register(api_client, password=password)
    assert response.status_code == 422


def test_login_returns_generic_errors_and_succeeds(
    api_client: TestClient,
) -> None:
    email = unique_email("login")
    assert register(api_client, email=email).status_code == 201
    api_client.cookies.clear()

    wrong_password = login(api_client, email=email, password="wrong-password-123")
    unknown_account = login(api_client, email=unique_email("missing"))
    assert wrong_password.status_code == 401
    assert unknown_account.status_code == 401
    assert wrong_password.json() == unknown_account.json()
    assert wrong_password.json()["error"]["message"] == "Invalid email or password."

    role_injection = api_client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": DEFAULT_PASSWORD,
            "role": "ADMINISTRATOR",
        },
    )
    assert role_injection.status_code == 422

    success = login(api_client, email=email)
    assert success.status_code == 200
    assert success.json()["user"]["email"] == email.lower()
    assert get_refresh_cookie(api_client)


def test_disabled_account_cannot_login_or_use_existing_access(
    api_client: TestClient, db_session: Session
) -> None:
    email = unique_email("disabled")
    registered = register(api_client, email=email)
    token = registered.json()["access_token"]

    user = _user_by_email(db_session, email)
    user.status = UserStatus.DISABLED.value
    db_session.commit()

    assert (
        api_client.get("/api/v1/auth/me", headers=bearer(token)).status_code
        == 401
    )
    denied_login = login(api_client, email=email)
    assert denied_login.status_code == 401
    assert denied_login.json()["error"]["message"] == "Invalid email or password."

    denied_refresh = api_client.post("/api/v1/auth/refresh")
    assert denied_refresh.status_code == 401
    assert denied_refresh.json()["error"]["message"] == "Session is invalid or has expired."

    db_session.expire_all()
    family_tokens = db_session.scalars(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    ).all()
    assert family_tokens
    assert all(token.revoked_at is not None for token in family_tokens)


def test_current_user_requires_a_valid_access_token(
    api_client: TestClient,
) -> None:
    missing = api_client.get("/api/v1/auth/me")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"

    malformed = api_client.get(
        "/api/v1/auth/me", headers=bearer("not-a-real-token")
    )
    assert malformed.status_code == 401

    registered = register(api_client, email=unique_email("me"))
    token = registered.json()["access_token"]
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.require_jwt_secret(),
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    payload["role"] = "ADMINISTRATOR"
    forged = jwt.encode(
        payload, "attacker-controlled-signing-key-0123456789", algorithm="HS256"
    )
    assert (
        api_client.get("/api/v1/auth/me", headers=bearer(forged)).status_code
        == 401
    )


def test_refresh_rotates_and_reuse_revokes_the_family(
    api_client: TestClient, db_session: Session
) -> None:
    email = unique_email("refresh")
    registered = register(api_client, email=email)
    old_access_token = registered.json()["access_token"]
    old_refresh = get_refresh_cookie(api_client)
    assert old_refresh

    rotated = api_client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    new_refresh = get_refresh_cookie(api_client)
    new_access_token = rotated.json()["access_token"]
    assert new_refresh and new_refresh != old_refresh
    assert new_access_token != old_access_token

    user = _user_by_email(db_session, email)
    old_row = db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(old_refresh)
        )
    )
    new_row = db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(new_refresh)
        )
    )
    assert old_row is not None and new_row is not None
    assert old_row.family_id == new_row.family_id
    assert old_row.revoked_at is not None
    assert old_row.replaced_by_id == new_row.id
    assert new_row.revoked_at is None
    assert (
        api_client.get(
            "/api/v1/auth/me", headers=bearer(new_access_token)
        ).status_code
        == 200
    )

    set_refresh_cookie(api_client, old_refresh)
    reused = api_client.post("/api/v1/auth/refresh")
    assert reused.status_code == 401
    assert reused.json()["error"]["message"] == "Session is invalid or has expired."

    db_session.expire_all()
    family_tokens = db_session.scalars(
        select(RefreshToken).where(
            RefreshToken.family_id == old_row.family_id,
        )
    ).all()
    assert len(family_tokens) == 2
    assert all(token.revoked_at is not None for token in family_tokens)

    set_refresh_cookie(api_client, new_refresh)
    assert api_client.post("/api/v1/auth/refresh").status_code == 401
    assert (
        api_client.get(
            "/api/v1/auth/me", headers=bearer(new_access_token)
        ).status_code
        == 401
    )


def test_expired_refresh_token_is_rejected(
    api_client: TestClient, db_session: Session
) -> None:
    registered = register(api_client, email=unique_email("expired"))
    assert registered.status_code == 201
    refresh = get_refresh_cookie(api_client)
    assert refresh

    stored = db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(refresh)
        )
    )
    assert stored is not None
    stored.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    response = api_client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    db_session.expire_all()
    assert stored.revoked_at is not None


def test_logout_revokes_refresh_and_access_immediately(
    api_client: TestClient,
) -> None:
    registered = register(api_client, email=unique_email("logout"))
    token = registered.json()["access_token"]
    refresh = get_refresh_cookie(api_client)

    logout = api_client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]

    assert (
        api_client.get("/api/v1/auth/me", headers=bearer(token)).status_code
        == 401
    )

    set_refresh_cookie(api_client, refresh or "")
    assert api_client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_requires_a_cookie(api_client: TestClient) -> None:
    api_client.cookies.clear()
    response = api_client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


def test_auth_origin_checks_block_cross_site_posts(
    api_client: TestClient,
) -> None:
    email = unique_email("origin")
    assert register(api_client, email=email).status_code == 201
    untrusted = {"Origin": "https://attacker.example"}

    blocked_login = login(
        api_client,
        email=email,
        headers=untrusted,
    )
    assert blocked_login.status_code == 403
    assert blocked_login.json()["error"]["message"] == "Request origin is not allowed."

    blocked_refresh = api_client.post("/api/v1/auth/refresh", headers=untrusted)
    assert blocked_refresh.status_code == 403

    trusted = api_client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "http://localhost:5173"},
    )
    assert trusted.status_code == 200


def test_auth_logs_do_not_contain_secrets_or_email(
    api_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    email = unique_email("logging")
    with caplog.at_level(logging.INFO, logger="trustvault.auth"):
        registered = register(api_client, email=email)

    token = registered.json()["access_token"]
    refresh = get_refresh_cookie(api_client) or ""
    logs = caplog.text

    assert "Login succeeded" not in logs
    assert DEFAULT_PASSWORD not in logs
    assert token not in logs
    assert refresh not in logs
    assert email not in logs
    assert "Account registered" in logs
