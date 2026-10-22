"""Safely check Supabase Storage connectivity and bucket access without printing secrets."""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.services.storage import (
    StorageConfigurationError,
    StorageOperationError,
    SupabaseStorage,
)


def main() -> int:
    settings = get_settings()
    storage = SupabaseStorage(settings)

    try:
        storage.check_connection()
    except StorageConfigurationError as exc:
        print(f"FAILED: {exc}")
        return 2
    except StorageOperationError as exc:
        print(f"FAILED: {exc}")
        return 1

    print(
        "OK: connected to private bucket "
        f"'{settings.supabase_storage_bucket}' at {settings.supabase_url}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
