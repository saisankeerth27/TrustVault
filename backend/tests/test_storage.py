from __future__ import annotations

import logging

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from app.core.config import Settings
from app.services.storage import (
    StorageConfigurationError,
    StorageObjectNotFoundError,
    StorageOperationError,
    WasabiStorage,
)


def configured_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "wasabi_endpoint_url": "https://s3.us-east-1.wasabisys.com",
        "wasabi_region": "us-east-1",
        "wasabi_bucket_name": "trustvault-test",
        "wasabi_access_key_id": "test-access-key",
        "wasabi_secret_access_key": "test-secret-key",
    }
    values.update(overrides)
    return Settings(**values)


def test_missing_wasabi_configuration_fails_closed(monkeypatch, caplog) -> None:
    for name in (
        "WASABI_ENDPOINT_URL",
        "WASABI_BUCKET_NAME",
        "WASABI_ACCESS_KEY_ID",
        "WASABI_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    storage = WasabiStorage(settings)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(StorageConfigurationError):
            storage.upload_bytes(
                key="documents/test/report.pdf",
                data=b"data",
                content_type="application/pdf",
            )

    assert "WASABI_ACCESS_KEY_ID" in caplog.text
    assert "test-secret" not in caplog.text


def test_wasabi_endpoint_must_use_https() -> None:
    with pytest.raises(ValidationError):
        configured_settings(wasabi_endpoint_url="http://s3.example.test")


@pytest.mark.parametrize("value", [0, -1, 101 * 1024 * 1024])
def test_upload_limit_is_bounded(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_upload_size_bytes=value)


def test_upload_extension_configuration_is_normalized() -> None:
    settings = Settings(
        _env_file=None,
        allowed_upload_extensions=" .PDF, TXT ,pdf ",
    )
    assert settings.allowed_upload_extension_set == {"pdf", "txt"}


def test_upload_extension_configuration_rejects_empty_values() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, allowed_upload_extensions=" , ")


def test_storage_failure_logs_only_a_safe_error_code(caplog) -> None:
    client_error = ClientError(
        {
            "Error": {
                "Code": "AccessDenied",
                "Message": "SECRET-CREDENTIAL-DETAIL",
            }
        },
        "PutObject",
    )

    class FailingClient:
        def put_object(self, **kwargs):
            raise client_error

    storage = WasabiStorage(configured_settings())
    storage._client = FailingClient()

    with caplog.at_level(logging.WARNING):
        with pytest.raises(StorageOperationError):
            storage.upload_bytes(
                key="documents/test/report.pdf",
                data=b"data",
                content_type="application/pdf",
            )

    assert "AccessDenied" in caplog.text
    assert "SECRET-CREDENTIAL-DETAIL" not in caplog.text


def test_storage_connection_check_is_wrapped_safely() -> None:
    client_error = ClientError(
        {"Error": {"Code": "NoSuchBucket", "Message": "SECRET-BUCKET-DETAIL"}},
        "HeadBucket",
    )

    class FailingClient:
        def head_bucket(self, **kwargs):
            raise client_error

    storage = WasabiStorage(configured_settings())
    storage._client = FailingClient()

    with pytest.raises(StorageOperationError) as exc_info:
        storage.check_connection()

    assert "SECRET-BUCKET-DETAIL" not in str(exc_info.value)


def test_storage_download_returns_private_object_body() -> None:
    body = object()

    class FakeClient:
        def get_object(self, **kwargs):
            assert kwargs == {
                "Bucket": "trustvault-test",
                "Key": "documents/test/report.pdf",
            }
            return {"Body": body}

    storage = WasabiStorage(configured_settings())
    storage._client = FakeClient()

    assert storage.open_download(key="documents/test/report.pdf") is body


@pytest.mark.parametrize(
    ("code", "expected_exception"),
    [
        ("NoSuchKey", StorageObjectNotFoundError),
        ("404", StorageObjectNotFoundError),
        ("AccessDenied", StorageOperationError),
    ],
)
def test_storage_download_errors_are_safe(
    code: str,
    expected_exception: type[Exception],
    caplog,
) -> None:
    client_error = ClientError(
        {"Error": {"Code": code, "Message": "SECRET-OBJECT-DETAIL"}},
        "GetObject",
    )

    class FailingClient:
        def get_object(self, **kwargs):
            raise client_error

    storage = WasabiStorage(configured_settings())
    storage._client = FailingClient()

    with caplog.at_level(logging.WARNING):
        with pytest.raises(expected_exception):
            storage.open_download(key="documents/test/report.pdf")

    assert code in caplog.text
    assert "SECRET-OBJECT-DETAIL" not in caplog.text


def test_storage_download_without_body_fails_closed() -> None:
    class FakeClient:
        def get_object(self, **kwargs):
            return {}

    storage = WasabiStorage(configured_settings())
    storage._client = FakeClient()

    with pytest.raises(StorageOperationError):
        storage.open_download(key="documents/test/report.pdf")


def test_storage_metadata_returns_only_safe_fields() -> None:
    class FakeClient:
        def head_object(self, **kwargs):
            return {
                "ContentLength": 42,
                "ContentType": "application/pdf",
                "ETag": '"etag"',
                "Metadata": {"secret": "value"},
            }

    storage = WasabiStorage(configured_settings())
    storage._client = FakeClient()

    assert storage.get_object_metadata(key="documents/test/report.pdf") == {
        "size": 42,
        "content_type": "application/pdf",
        "etag": '"etag"',
    }
