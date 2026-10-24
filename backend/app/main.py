from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import RequestIdMiddleware
from app.core.request_limits import (
    UPLOAD_CONTENT_LENGTH_OVERHEAD_BYTES,
    UploadSizeLimitMiddleware,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), camera=(), microphone=()"
        )
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "TrustVault API. Authentication is available under /api/v1/auth. Secure upload, "
            "document listing/search, metadata management, proxied download, soft deletion, and "
            "owner-managed READ/EDIT permissions are available under /api/v1/documents. "
            "Administrator account management, document metadata oversight, audit history, and "
            "integrity verification are available under /api/v1/admin."
        ),
    )

    app.add_middleware(
        UploadSizeLimitMiddleware,
        max_body_bytes=settings.max_upload_size_bytes
        + UPLOAD_CONTENT_LENGTH_OVERHEAD_BYTES,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    # Starlette applies the most recently added middleware outermost. Keep CORS
    # outermost so browser clients receive CORS headers even when an inner
    # middleware or the API returns an authentication error.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)

    return app


app = create_app()
