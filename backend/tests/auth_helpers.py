from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

DEFAULT_PASSWORD = "correct horse battery staple"
REFRESH_COOKIE = "trustvault_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid4().hex}@example.com"


def register(
    client: TestClient,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    name: str = "Test User",
):
    return client.post(
        "/api/v1/auth/register",
        json={
            "name": name,
            "email": email or unique_email(),
            "password": password,
        },
    )


def login(
    client: TestClient,
    *,
    email: str,
    password: str = DEFAULT_PASSWORD,
    headers: dict[str, str] | None = None,
):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def set_refresh_cookie(client: TestClient, value: str) -> None:
    client.cookies.set(REFRESH_COOKIE, value, path=REFRESH_COOKIE_PATH)


def get_refresh_cookie(client: TestClient) -> str | None:
    return client.cookies.get(REFRESH_COOKIE)
