from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.rate_limit import auth_rate_limiter
from tests.auth_helpers import DEFAULT_PASSWORD, login, register, unique_email


def test_login_attempts_are_rate_limited(api_client: TestClient) -> None:
    email = unique_email("ratelimit-login")
    assert register(api_client, email=email).status_code == 201

    for _ in range(10):
        response = login(api_client, email=email, password="wrong-password-123")
        assert response.status_code == 401

    blocked = login(api_client, email=email)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1

    auth_rate_limiter.reset()
    assert login(api_client, email=email).status_code == 200


def test_registration_attempts_are_rate_limited(api_client: TestClient) -> None:
    for index in range(10):
        response = register(api_client, email=unique_email(f"ratelimit-reg-{index}"))
        assert response.status_code == 201

    blocked = register(api_client, email=unique_email("ratelimit-reg-blocked"))
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1

    auth_rate_limiter.reset()
    assert (
        register(api_client, email=unique_email("ratelimit-reg-allowed")).status_code
        == 201
    )


def test_rate_limit_response_does_not_leak_credentials(
    api_client: TestClient,
) -> None:
    email = unique_email("ratelimit-secret")
    assert register(api_client, email=email).status_code == 201

    for _ in range(10):
        login(api_client, email=email, password=DEFAULT_PASSWORD + "-wrong")

    response = login(api_client, email=email, password=DEFAULT_PASSWORD)
    assert response.status_code == 429
    body = response.text
    assert DEFAULT_PASSWORD not in body
    assert email not in body
