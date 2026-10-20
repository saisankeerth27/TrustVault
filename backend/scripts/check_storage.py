"""Safely check Wasabi connectivity and bucket access without printing secrets."""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.services.storage import (
    StorageConfigurationError,
    StorageOperationError,
    WasabiStorage,
)


def main() -> int:
    settings = get_settings()
    storage = WasabiStorage(settings)

    try:
        storage.check_connection()
    except StorageConfigurationError as exc:
        print(f"FAILED: {exc}")
        return 2
    except StorageOperationError as exc:
        print(f"FAILED: {exc}")
        return 1

    print(
        "OK: connected to bucket "
        f"'{settings.wasabi_bucket_name}' at {settings.wasabi_endpoint_url} "
        f"(region {settings.wasabi_region})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
