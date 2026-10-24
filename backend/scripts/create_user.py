"""Create a TrustVault account explicitly.

Usage (from backend/):
    python -m scripts.create_user --email admin@example.com --name "Admin" \
        --role ADMINISTRATOR

The password is read from TRUSTVAULT_USER_PASSWORD or an interactive prompt.
The command never prints the password or hash and never resets an existing user.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from uuid import UUID

import httpx
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import get_settings
from app.core.security import validate_password_strength
from app.db.session import get_session_factory
from app.models.enums import UserRole, UserStatus
from app.models.user import User

_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def _admin_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }


def _create_supabase_user(
    base_url: str,
    service_key: str,
    *,
    email: str,
    name: str,
    password: str,
) -> UUID:
    try:
        response = httpx.post(
            f"{base_url}/auth/v1/admin/users",
            headers=_admin_headers(service_key),
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name},
            },
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("id"), str):
            raise RuntimeError("Supabase Auth returned an invalid user identity.")
        return UUID(body["id"])
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Supabase Auth could not create the account.") from exc


def _delete_supabase_user(base_url: str, service_key: str, user_id: UUID) -> None:
    response = httpx.delete(
        f"{base_url}/auth/v1/admin/users/{user_id}",
        headers=_admin_headers(service_key),
        timeout=_TIMEOUT,
    )
    response.raise_for_status()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a TrustVault account.")
    parser.add_argument("--email", required=True, help="Account email address.")
    parser.add_argument("--name", required=True, help="Display name.")
    parser.add_argument(
        "--role",
        required=True,
        choices=[role.value for role in UserRole],
        help="Trusted account role.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    name = args.name.strip()
    if not name or len(name) > 255:
        print("Error: name must be between 1 and 255 characters.", file=sys.stderr)
        return 2

    try:
        email = str(_EMAIL_ADAPTER.validate_python(args.email)).strip().lower()
    except ValidationError:
        print("Error: enter a valid email address.", file=sys.stderr)
        return 2

    password = os.getenv("TRUSTVAULT_USER_PASSWORD")
    if not password:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm password: "):
            print("Error: passwords do not match.", file=sys.stderr)
            return 2

    try:
        validate_password_strength(password)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print(
            "Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured.",
            file=sys.stderr,
        )
        return 2

    try:
        session_factory = get_session_factory()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    service_key = settings.supabase_service_role_key.get_secret_value()
    with session_factory() as session:
        if session.scalar(select(User.id).where(User.email == email)) is not None:
            print("Error: an account with that email already exists.", file=sys.stderr)
            return 1

        try:
            provider_id = _create_supabase_user(
                settings.supabase_url,
                service_key,
                email=email,
                name=name,
                password=password,
            )
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        user = User(
            name=name,
            email=email.strip().lower(),
            password_hash=None,
            supabase_auth_id=provider_id,
            role=UserRole(args.role).value,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        try:
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            try:
                _delete_supabase_user(settings.supabase_url, service_key, provider_id)
            except httpx.HTTPError:
                print(
                    "Error: account creation failed; remove the orphaned Supabase "
                    "Auth identity using the Auth dashboard.",
                    file=sys.stderr,
                )
                return 1
            if isinstance(exc, IntegrityError):
                print(
                    "Error: an account with that email already exists.",
                    file=sys.stderr,
                )
            else:
                print(
                    "Error: the TrustVault account could not be saved.",
                    file=sys.stderr,
                )
            return 1

        print(f"Created TrustVault {user.role} account (id={user.id}).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
