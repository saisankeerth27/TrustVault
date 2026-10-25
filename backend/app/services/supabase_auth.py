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
        provider_error: str | None = None,
    ) -> None:
        super().__init__("Supabase Auth request failed.")
        self.status_code = status_code
        self.configuration_missing = configuration_missing
        self.provider_error = provider_error


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
        provider_error = None
        try:
            body = response.json()
            if isinstance(body, dict):
                provider_error = body.get("msg") or body.get("error") or body.get("error_description")
        except ValueError:
            pass
        raise SupabaseAuthError(response.status_code, provider_error=provider_error) from None
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


def is_email_confirmed(user: dict[str, Any]) -> bool:
    """Return True when Supabase reports the account's email as verified."""

    metadata = user.get("user_metadata")
    metadata_verified = (
        metadata.get("email_verified") if isinstance(metadata, dict) else False
    )
    return bool(
        user.get("email_confirmed_at")
        or user.get("confirmed_at")
        or user.get("email_verified")
        or metadata_verified
    )


def find_user_by_email(email: str) -> dict[str, Any] | None:
    """Look up a Supabase Auth user by email using the service role.

    TrustVault only creates its own profile after OTP verification, so the
    local ``users`` table cannot tell us whether Supabase already holds an
    unconfirmed account for an address. This lookup closes that gap.

    Returns the provider user when it exists and ``None`` only when the
    provider answered successfully and holds no account for the address.
    A failed or unconfigured lookup raises :class:`SupabaseAuthError`, so
    callers can tell "definitely absent" from "could not check" before they
    decide whether a local profile still has a usable provider account.
    """

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SupabaseAuthError(configuration_missing=True)

    target = email.strip().lower()
    service_key = settings.supabase_service_role_key.get_secret_value()
    base_url = settings.supabase_url.rstrip("/")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(
            base_url=f"{base_url}/auth/v1/",
            headers=headers,
            timeout=httpx.Timeout(15.0, connect=5.0),
        ) as client:
            # GoTrue's admin listing is paginated and does not guarantee an
            # email filter on every version, so scan a bounded number of
            # pages and match exactly.
            for page in range(1, 11):
                response = client.get(
                    "admin/users",
                    params={"page": page, "per_page": 200},
                )
                if not response.is_success:
                    raise SupabaseAuthError(response.status_code)
                body = response.json()
                users = body.get("users") if isinstance(body, dict) else body
                if not isinstance(users, list):
                    raise SupabaseAuthError()
                for user in users:
                    candidate = user.get("email") if isinstance(user, dict) else None
                    if (
                        isinstance(candidate, str)
                        and candidate.strip().lower() == target
                    ):
                        return user
                if len(users) < 200:
                    return None
    except (httpx.HTTPError, ValueError) as exc:
        raise SupabaseAuthError() from exc
    return None


def create_user(
    email: str,
    password: str,
    name: str,
) -> dict[str, Any]:
    """Create an unconfirmed Supabase Auth user with the service role.

    ``POST /signup`` always sends the *Confirm signup* template, so the
    deployment cannot choose which email the user receives. Creating the user
    through the admin API does not send anything, which lets the caller issue
    the code through ``POST /otp`` (the *Magic Link* template) while still
    storing the submitted password for later sign-in.

    The account stays unconfirmed (``email_confirm: false``), so password
    login is rejected until the emailed code is verified.
    """

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SupabaseAuthError(configuration_missing=True)

    service_key = settings.supabase_service_role_key.get_secret_value()
    base_url = settings.supabase_url.rstrip("/")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }

    try:
        response = httpx.post(
            f"{base_url}/auth/v1/admin/users",
            headers=headers,
            json={
                "email": email,
                "password": password,
                "email_confirm": False,
                "user_metadata": {"name": name},
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SupabaseAuthError() from exc

    if not response.is_success:
        provider_error = None
        try:
            body = response.json()
            if isinstance(body, dict):
                provider_error = (
                    body.get("msg")
                    or body.get("error_description")
                    or body.get("error")
                    or body.get("error_code")
                )
        except ValueError:
            pass
        raise SupabaseAuthError(
            response.status_code,
            provider_error=provider_error,
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise SupabaseAuthError(response.status_code) from exc
    if not isinstance(body, dict):
        raise SupabaseAuthError(response.status_code)
    return body


def sign_up(
    email: str,
    password: str,
    name: str,
    redirect_to: str | None,
) -> dict[str, Any]:
    """Create a new user and ask Supabase to send the confirmation email.

    Kept for deployments that use the *Confirm signup* template. TrustVault's
    registration route uses :func:`create_user` plus :func:`sign_in_with_otp`
    so the email comes from the *Magic Link* template instead.
    """
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


def verify_signup_otp(email: str, token: str) -> dict[str, Any]:
    """Confirm a new account with the code issued by ``POST /otp``.

    Accounts are created unconfirmed through the admin API and the code is
    issued as a magic-link token, so GoTrue expects type ``magiclink``.
    Verifying it also sets ``email_confirmed_at`` and returns a session.
    """
    return _request(
        "POST",
        "verify",
        payload={"email": email, "token": token, "type": "magiclink"},
    )


def sign_in_with_otp(email: str, redirect_to: str | None = None) -> None:
    """Send the project's *Magic Link* email (8-digit code and link).

    ``create_user`` is false so this never silently creates an account: the
    registration route creates the user first, then calls this to issue the
    code. ``redirect_to`` controls where the emailed link lands.
    """

    params = {"redirect_to": redirect_to} if redirect_to else None
    _request(
        "POST",
        "otp",
        payload={"email": email, "create_user": False},
        params=params,
    )


def verify_otp_login(email: str, token: str) -> dict[str, Any]:
    """Verify a passwordless email OTP (GoTrue type "email", not signup/recovery)."""
    return _request(
        "POST",
        "verify",
        payload={"email": email, "token": token, "type": "email"},
    )


def update_recovery_password(access_token: str, password: str) -> dict[str, Any]:
    return _request(
        "PUT",
        "user",
        access_token=access_token,
        payload={"password": password},
    )


def delete_supabase_user(user_id: str | Any) -> None:
    """Permanently delete a user from Supabase Auth via admin API."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return
    service_key = settings.supabase_service_role_key.get_secret_value()
    base_url = settings.supabase_url
    try:
        with httpx.Client(
            base_url=f"{base_url}/auth/v1/",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(15.0, connect=5.0),
        ) as client:
            client.delete(f"admin/users/{user_id}")
    except Exception:
        # Best-effort deletion in external provider
        pass
