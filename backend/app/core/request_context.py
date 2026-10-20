"""Request correlation IDs propagated through logs and audit events."""

from __future__ import annotations

import ipaddress
import re
from contextvars import ContextVar
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_HEADER = b"x-request-id"
_USER_AGENT_HEADER = b"user-agent"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_request_id: ContextVar[str | None] = ContextVar("trustvault_request_id", default=None)
_client_metadata: ContextVar[dict[str, str] | None] = ContextVar(
    "trustvault_client_metadata",
    default=None,
)


def get_request_id() -> str | None:
    return _request_id.get()


def get_request_metadata() -> dict[str, str]:
    metadata = _client_metadata.get()
    return dict(metadata) if metadata else {}


def _request_id_from_scope(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name.lower() != _REQUEST_ID_HEADER:
            continue
        try:
            candidate = value.decode("ascii")
        except UnicodeDecodeError:
            break
        if _VALID_REQUEST_ID.fullmatch(candidate):
            return candidate
        break
    return uuid4().hex


def _client_ip_from_scope(scope: Scope) -> str | None:
    client = scope.get("client")
    if not client:
        return None
    host = client[0]
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def _user_agent_from_scope(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name.lower() != _USER_AGENT_HEADER:
            continue
        decoded = value.decode("utf-8", errors="replace")
        printable = "".join(character for character in decoded if character.isprintable())
        return printable[:512] or None
    return None


def _client_metadata_from_scope(scope: Scope) -> dict[str, str]:
    metadata: dict[str, str] = {}
    client_ip = _client_ip_from_scope(scope)
    if client_ip:
        metadata["client_ip"] = client_ip
    user_agent = _user_agent_from_scope(scope)
    if user_agent:
        metadata["user_agent"] = user_agent
    return metadata


class RequestIdMiddleware:
    """Accept a safe correlation ID or generate one and echo it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from_scope(scope)
        request_token = _request_id.set(request_id)
        metadata_token = _client_metadata.set(_client_metadata_from_scope(scope))

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((_REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _client_metadata.reset(metadata_token)
            _request_id.reset(request_token)
