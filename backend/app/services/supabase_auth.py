"""Server-side calls to Supabase Auth's supported HTTP endpoints."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings

# Email-backed sign-up and recovery calls can take longer than token validation.
# Keep a bounded timeout, but avoid treating a healthy provider's slower mail
# dispatch as an immediate service failure.
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class SupabaseAuthError(Exception):
    """A safe-to-report failure from Supabase Auth."""

    def __init__(
        self,
        status_code: int | None = None,
        *,
        configuration_missing: bool = False,
    ) -> None:
        super().__init__("Supabase Auth request failed.")
        self.status_code = status_code
        self.configuration_missing = configuration_missing


def _request(
    method: str,
    path: str,
    *,
    access_token: str | None = None,
    payload: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        base_url, anon_key = get_settings().require_supabase_auth()
    except RuntimeError as exc:
        raise SupabaseAuthError(configuration_missing=True) from exc
    headers = {"apikey": anon_key, "Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    try:
        response = httpx.request(
            method,
            f"{base_url}/auth/v1/{path}",
            headers=headers,
            json=payload,
            params=params,
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SupabaseAuthError from exc

    if not response.is_success:
        raise SupabaseAuthError(response.status_code)
    if response.status_code == 204 or not response.content:
        return {}
    try:
        body = response.json()
    except ValueError as exc:
        raise SupabaseAuthError(response.status_code) from exc
    if not isinstance(body, dict):
        raise SupabaseAuthError(response.status_code)
    return body


def get_user(access_token: str) -> dict[str, Any]:
    return _request("GET", "user", access_token=access_token)


def sign_up(
    email: str,
    password: str,
    name: str,
    redirect_to: str | None,
) -> dict[str, Any]:
    params = {"redirect_to": redirect_to} if redirect_to else None
    return _request(
        "POST",
        "signup",
        payload={
            "email": email,
            "password": password,
            "data": {"name": name},
        },
        params=params,
    )


def sign_in_with_password(email: str, password: str) -> dict[str, Any]:
    return _request(
        "POST",
        "token",
        payload={"email": email, "password": password},
        params={"grant_type": "password"},
    )


def resend_signup_confirmation(email: str, redirect_to: str) -> None:
    """Request a replacement confirmation email without exposing account state."""

    _request(
        "POST",
        "resend",
        payload={"type": "signup", "email": email},
        params={"redirect_to": redirect_to},
    )


def request_password_recovery(email: str, redirect_to: str) -> None:
    _request(
        "POST",
        "recover",
        payload={"email": email},
        params={"redirect_to": redirect_to},
    )


def verify_recovery_otp(email: str, token: str) -> dict[str, Any]:
    return _request(
        "POST",
        "verify",
        payload={"email": email, "token": token, "type": "recovery"},
    )


def update_recovery_password(access_token: str, password: str) -> dict[str, Any]:
    return _request(
        "PUT",
        "user",
        access_token=access_token,
        payload={"password": password},
    )
