from __future__ import annotations

import asyncio
import json

import pytest

from app.core.request_limits import UploadSizeLimitMiddleware

UPLOAD_PATH = "/api/v1/documents/upload"


def _run_middleware(headers: list[tuple[bytes, bytes]]) -> tuple[bool, list[dict]]:
    inner_called = False
    messages: list[dict] = []

    async def inner(scope, receive, send) -> None:
        nonlocal inner_called
        inner_called = True

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        messages.append(message)

    middleware = UploadSizeLimitMiddleware(inner, max_body_bytes=100)
    scope = {
        "type": "http",
        "method": "POST",
        "path": UPLOAD_PATH,
        "headers": headers,
    }
    asyncio.run(middleware(scope, receive, send))
    return inner_called, messages


@pytest.mark.parametrize(
    ("headers", "status_code", "code"),
    [
        ([], 411, "length_required"),
        ([(b"content-length", b"abc")], 400, "bad_request"),
        (
            [
                (b"content-length", b"50"),
                (b"content-length", b"60"),
            ],
            400,
            "bad_request",
        ),
        ([(b"content-length", b"101")], 413, "payload_too_large"),
    ],
)
def test_rejects_missing_invalid_duplicate_or_oversized_lengths(
    headers: list[tuple[bytes, bytes]],
    status_code: int,
    code: str,
) -> None:
    inner_called, messages = _run_middleware(headers)

    assert inner_called is False
    assert messages[0]["status"] == status_code
    assert json.loads(messages[1]["body"])["error"]["code"] == code


def test_allows_request_at_limit_to_reach_the_application() -> None:
    inner_called, messages = _run_middleware([(b"content-length", b"100")])

    assert inner_called is True
    assert messages == []
