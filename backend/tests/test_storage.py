from __future__ import annotations

import logging

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.storage import (
    StorageConfigurationError,
    StorageObjectNotFoundError,
    StorageOperationError,
    SupabaseStorage,
)


def configured_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "supabase_url": "https://example.supabase.co",
        "supabase_storage_bucket": "trustvault-test",
        "supabase_service_role_key": "service-role-test",
    }
    values.update(overrides)
    return Settings(**values)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        json_data: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._json_data = json_data or {}

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict[str, object]:
        return self._json_data


class FakeClient:
    def __init__(
        self,
        response: FakeResponse | None = None,
        error: httpx.HTTPError | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.method = ""
        self.url = ""
        self.headers: dict[str, str] = {}
        self.content = b""

    def _call(self, method: str, url: str, **kwargs) -> FakeResponse:
        self.method = method
        self.url = url
        self.headers = kwargs.get("headers", {})
        self.content = kwargs.get("content", b"")
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("A fake response is required.")
        return self.response

    def post(self, url: str, **kwargs) -> FakeResponse:
        return self._call("POST", url, **kwargs)

    def get(self, url: str, **kwargs) -> FakeResponse:
        return self._call("GET", url, **kwargs)

    def delete(self, url: str, **kwargs) -> FakeResponse:
        return self._call("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs) -> FakeResponse:
        return self._call("HEAD", url, **kwargs)


def test_missing_supabase_configuration_fails_closed(monkeypatch, caplog) -> None:
    for name in (
        "SUPABASE_URL",
        "SUPABASE_STORAGE_BUCKET",
        "SUPABASE_SERVICE_ROLE_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    storage = SupabaseStorage(settings)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(StorageConfigurationError):
            storage.upload_bytes(
                key="documents/test/report.pdf",
                data=b"data",
                content_type="application/pdf",
            )

    assert "SUPABASE_SERVICE_ROLE_KEY" in caplog.text
    assert "service-role-test" not in caplog.text


def test_supabase_url_must_use_https() -> None:
    with pytest.raises(ValidationError):
        configured_settings(supabase_url="http://example.supabase.co")


def test_supabase_url_must_not_include_a_path() -> None:
    with pytest.raises(ValidationError):
        configured_settings(supabase_url="https://example.supabase.co/storage/v1")


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


def test_new_secret_key_is_sent_only_in_apikey_header() -> None:
    client = FakeClient(FakeResponse(200))
    storage = SupabaseStorage(configured_settings(supabase_service_role_key="sb_secret_test"))
    storage._client = client

    storage.upload_bytes(
        key="documents/test/report.pdf",
        data=b"data",
        content_type="application/pdf",
    )

    assert client.method == "POST"
    assert client.url == (
        "https://example.supabase.co/storage/v1/object/"
        "trustvault-test/documents/test/report.pdf"
    )
    assert client.headers["apikey"] == "sb_secret_test"
    assert "Authorization" not in client.headers
    assert client.content == b"data"


def test_legacy_service_role_key_is_sent_in_both_headers() -> None:
    client = FakeClient(FakeResponse(200))
    storage = SupabaseStorage(configured_settings())
    storage._client = client

    storage.upload_bytes(
        key="documents/test/report.pdf",
        data=b"data",
        content_type="application/pdf",
    )

    assert client.headers["apikey"] == "service-role-test"
    assert client.headers["Authorization"] == "Bearer service-role-test"


def test_storage_failure_logs_only_an_http_status(caplog) -> None:
    client = FakeClient(FakeResponse(403, content=b"SECRET-CREDENTIAL-DETAIL"))
    storage = SupabaseStorage(configured_settings())
    storage._client = client

    with caplog.at_level(logging.WARNING):
        with pytest.raises(StorageOperationError):
            storage.upload_bytes(
                key="documents/test/report.pdf",
                data=b"data",
                content_type="application/pdf",
            )

    assert "HTTP 403" in caplog.text
    assert "SECRET-CREDENTIAL-DETAIL" not in caplog.text


def test_storage_connection_error_is_wrapped_safely() -> None:
    storage = SupabaseStorage(configured_settings())
    storage._client = FakeClient(error=httpx.ConnectError("SECRET-CONNECTION-DETAIL"))

    with pytest.raises(StorageOperationError) as exc_info:
        storage.check_connection()

    assert "SECRET-CONNECTION-DETAIL" not in str(exc_info.value)


def test_connection_check_rejects_a_public_bucket() -> None:
    storage = SupabaseStorage(configured_settings())
    storage._client = FakeClient(FakeResponse(200, json_data={"public": True}))

    with pytest.raises(StorageConfigurationError):
        storage.check_connection()


def test_connection_check_accepts_a_private_bucket() -> None:
    storage = SupabaseStorage(configured_settings())
    storage._client = FakeClient(FakeResponse(200, json_data={"public": False}))

    storage.check_connection()


def test_storage_download_returns_private_object_bytes() -> None:
    storage = SupabaseStorage(configured_settings())
    storage._client = FakeClient(FakeResponse(200, content=b"document-data"))

    body = storage.open_download(key="documents/test/report.pdf")

    assert body.read() == b"document-data"


@pytest.mark.parametrize(
    ("status_code", "json_data", "expected_exception"),
    [
        (404, None, StorageObjectNotFoundError),
        (400, {"statusCode": "404", "code": "NoSuchKey"}, StorageObjectNotFoundError),
        (403, None, StorageOperationError),
    ],
)
def test_storage_download_errors_are_safe(
    status_code: int,
    json_data: dict[str, object] | None,
    expected_exception: type[Exception],
    caplog,
) -> None:
    storage = SupabaseStorage(configured_settings())
    storage._client = FakeClient(
        FakeResponse(
            status_code,
            content=b"SECRET-OBJECT-DETAIL",
            json_data=json_data,
        )
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(expected_exception):
            storage.open_download(key="documents/test/report.pdf")

    assert f"HTTP {status_code}" in caplog.text
    assert "SECRET-OBJECT-DETAIL" not in caplog.text


def test_storage_delete_reports_a_missing_object() -> None:
    storage = SupabaseStorage(configured_settings())
    storage._client = FakeClient(
        FakeResponse(
            400,
            json_data={"statusCode": "404", "code": "NoSuchKey"},
        )
    )

    with pytest.raises(StorageObjectNotFoundError):
        storage.delete_object(key="documents/test/report.pdf")


def test_storage_metadata_returns_only_safe_fields() -> None:
    storage = SupabaseStorage(configured_settings())
    storage._client = FakeClient(
        FakeResponse(
            200,
            headers={
                "content-length": "42",
                "content-type": "application/pdf",
                "etag": '"etag"',
                "x-secret": "value",
            },
        )
    )

    assert storage.get_object_metadata(key="documents/test/report.pdf") == {
        "size": "42",
        "content_type": "application/pdf",
        "etag": '"etag"',
    }
