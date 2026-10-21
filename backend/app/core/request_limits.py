"""Pre-routing request size checks for upload endpoints."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

UPLOAD_CONTENT_LENGTH_OVERHEAD_BYTES = 1024 * 1024
_UPLOAD_PATH = "/api/v1/documents/upload"


class UploadSizeLimitMiddleware:
    """Reject oversized uploads before FastAPI parses or authenticates them."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path", "").rstrip("/") != _UPLOAD_PATH
        ):
            await self.app(scope, receive, send)
            return

        lengths = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"content-length"
        ]
        if not lengths:
            await _reject(
                scope,
                receive,
                send,
                status_code=411,
                code="length_required",
                message="A Content-Length header is required for uploads.",
            )
            return
        if len(lengths) > 1:
            await _reject(
                scope,
                receive,
                send,
                status_code=400,
                code="bad_request",
                message="The Content-Length header is invalid.",
            )
            return

        try:
            raw_length = lengths[0].decode("ascii")
            if not raw_length.isdigit():
                raise ValueError
            declared_length = int(raw_length)
        except (UnicodeDecodeError, ValueError):
            await _reject(
                scope,
                receive,
                send,
                status_code=400,
                code="bad_request",
                message="The Content-Length header is invalid.",
            )
            return

        if declared_length > self.max_body_bytes:
            await _reject(
                scope,
                receive,
                send,
                status_code=413,
                code="payload_too_large",
                message="The selected file is too large.",
            )
            return

        await self.app(scope, receive, send)


async def _reject(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    status_code: int,
    code: str,
    message: str,
) -> None:
    response = JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
    await response(scope, receive, send)
