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

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.security import validate_password_strength
from app.db.session import get_session_factory
from app.models.enums import UserRole
from app.services.auth import AccountExistsError, create_account

_EMAIL_ADAPTER = TypeAdapter(EmailStr)


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
        email = str(_EMAIL_ADAPTER.validate_python(args.email))
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

    try:
        session_factory = get_session_factory()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    with session_factory() as session:
        try:
            user = create_account(
                session,
                name=name,
                email=email,
                password=password,
                role=UserRole(args.role),
            )
        except AccountExistsError:
            print("Error: an account with that email already exists.", file=sys.stderr)
            return 1

        session.commit()
        print(f"Created user {user.email} with role {user.role} (id={user.id}).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
