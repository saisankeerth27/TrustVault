"""Create Supabase Auth identities for existing TrustVault accounts.

Run after Alembic upgrade and before enabling the Supabase-backed application.
The script reads only account IDs, names, and email addresses; it never exports
legacy password hashes or roles to Supabase Auth.
"""

from __future__ import annotations

import sys
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.user import User


def list_auth_emails(base_url: str, service_key: str) -> set[str]:
    emails: set[str] = set()
    page = 1
    with httpx.Client(
        base_url=f"{base_url}/auth/v1/",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Accept": "application/json",
        },
        timeout=httpx.Timeout(15.0, connect=5.0),
    ) as client:
        while True:
            response = client.get("admin/users", params={"page": page, "per_page": 500})
            response.raise_for_status()
            body: Any = response.json()
            users = body.get("users") if isinstance(body, dict) else None
            if not isinstance(users, list):
                raise RuntimeError("Supabase Admin API returned an invalid user list.")
            for auth_user in users:
                if isinstance(auth_user, dict) and isinstance(auth_user.get("email"), str):
                    emails.add(auth_user["email"].strip().lower())
            if len(users) < 500:
                return emails
            page += 1


def create_auth_identity(
    base_url: str,
    service_key: str,
    user: User,
) -> None:
    with httpx.Client(
        base_url=f"{base_url}/auth/v1/",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Accept": "application/json",
        },
        timeout=httpx.Timeout(15.0, connect=5.0),
    ) as client:
        response = client.post(
            "admin/users",
            json={
                "email": user.email,
                "email_confirm": True,
                "user_metadata": {"name": user.name},
            },
        )
        response.raise_for_status()


def main() -> int:
    settings = get_settings()
    try:
        if not settings.database_url or not settings.supabase_url:
            raise RuntimeError("DATABASE_URL and SUPABASE_URL must be configured.")
        if not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY must be configured.")

        service_key = settings.supabase_service_role_key.get_secret_value()
        existing_emails = list_auth_emails(settings.supabase_url, service_key)
        factory = get_session_factory()
        created = 0
        skipped = 0
        with factory() as session:
            users = session.scalars(select(User).order_by(User.created_at)).all()
            for index, user in enumerate(users, start=1):
                email = user.email.strip().lower()
                if email in existing_emails:
                    skipped += 1
                    continue
                try:
                    create_auth_identity(settings.supabase_url, service_key, user)
                except httpx.HTTPError as exc:
                    raise RuntimeError(
                        f"Supabase Auth import stopped at account {index}; "
                        "no email or credential values were logged."
                    ) from exc
                existing_emails.add(email)
                created += 1
        print(
            f"Supabase Auth identity import completed: {created} created, "
            f"{skipped} already present."
        )
        return 0
    except (RuntimeError, httpx.HTTPError) as exc:
        print(f"Supabase Auth identity import failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
