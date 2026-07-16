"""Authentication, rate limiting, and response hardening."""

import secrets
import time
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Security(api_key_header)) -> None:
    """Protect API routes when API_AUTH_TOKEN is configured."""
    expected = settings.api_auth_token
    if expected is None:
        return
    if api_key is None or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required.",
        )


class RequestSizeLimitMiddleware:
    """Bound declared and chunked request bodies before framework parsing."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        try:
            if content_length is not None and int(content_length) > self.max_bytes:
                await self._reject(scope, receive, send)
                return
        except ValueError:
            await self._reject(scope, receive, send, "Invalid Content-Length header.")
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        delivered = False

        async def replay_receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {
                "type": "http.request",
                "body": bytes(body),
                "more_body": False,
            }

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(
        scope,
        receive,
        send,
        detail: str = "Request body is too large.",
    ):
        response = JSONResponse({"detail": detail}, status_code=413)
        await response(scope, receive, send)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        if settings.production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Single-process safeguard; use a shared gateway limiter when scaling."""

    def __init__(self, app, requests_per_minute: int):
        super().__init__(app)
        self.limit = requests_per_minute
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()
        self.last_cleanup = time.monotonic()

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/", "/health/live", "/health/ready", "/favicon.ico"}:
            return await call_next(request)
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - 60
        with self.lock:
            if now - self.last_cleanup >= 60:
                for key in list(self.events):
                    queue = self.events[key]
                    while queue and queue[0] <= cutoff:
                        queue.popleft()
                    if not queue:
                        del self.events[key]
                self.last_cleanup = now

            events = self.events[client]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return JSONResponse(
                    {"detail": "Rate limit exceeded. Try again shortly."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            events.append(now)
            remaining = max(0, self.limit - len(events))

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
