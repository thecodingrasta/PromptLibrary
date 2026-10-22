"""Bound browser requests before authentication or application-side writes."""

import base64
import binascii
import secrets
import time
from urllib.parse import urlsplit
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from promptlibrary.config import Settings


def authority(value: str, scheme: str) -> tuple[str, int]:
    """Normalise ports and IPv6 without accepting credentials or malformed hosts."""
    parsed = urlsplit(f"{scheme}://{value}")
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid authority.")
    return parsed.hostname.lower(), parsed.port or (443 if scheme == "https" else 80)


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        path = scope["path"]
        started_at = time.perf_counter()
        request_id = uuid4().hex[:12]

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                outgoing = MutableHeaders(scope=message)
                outgoing["X-Request-ID"] = request_id
                outgoing["X-Response-Time"] = f"{(time.perf_counter() - started_at) * 1000:.1f}ms"
                outgoing["X-Content-Type-Options"] = "nosniff"
                outgoing["X-Frame-Options"] = "DENY"
                outgoing["Referrer-Policy"] = "no-referrer"
                outgoing["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                outgoing["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
                    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
                )
                if not path.startswith("/static/"):
                    outgoing["Cache-Control"] = "no-store"
            await send(message)

        async def reject(message: str, status: int, extra: dict[str, str] | None = None) -> None:
            await PlainTextResponse(message, status, headers=extra)(scope, receive, secure_send)

        try:
            scheme = scope.get("scheme", "http")
            expected_host = authority(headers.get("host", ""), scheme)
            allowed = {host.lower().strip("[]") for host in self.settings.allowed_hosts}
            if expected_host[0] not in allowed:
                raise ValueError("Untrusted host.")
        except ValueError:
            await reject("Invalid or untrusted Host header.", 400)
            return

        if self.settings.auth_password and path != "/health":
            authenticated = False
            try:
                auth_scheme, encoded = headers.get("authorization", "").split(" ", 1)
                if auth_scheme.lower() == "basic":
                    user, password = (
                        base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
                    )
                    authenticated = secrets.compare_digest(
                        user.encode(), self.settings.auth_username.encode()
                    )
                    authenticated &= secrets.compare_digest(
                        password.encode(), self.settings.auth_password.get_secret_value().encode()
                    )
            except (ValueError, UnicodeError, binascii.Error):
                authenticated = False
            if not authenticated:
                await reject(
                    "Authentication required.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="PromptLibrary", charset="UTF-8"'},
                )
                return

        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            origin = headers.get("origin")
            try:
                if origin:
                    parsed = urlsplit(origin)
                    actual = authority(parsed.netloc, parsed.scheme)
                    trusted_origins = {(scheme, expected_host)}
                    if self.settings.public_origin:
                        public = urlsplit(self.settings.public_origin)
                        trusted_origins.add(
                            (public.scheme, authority(public.netloc, public.scheme))
                        )
                    if (
                        (parsed.scheme, actual) not in trusted_origins
                        or parsed.path
                        or parsed.query
                        or parsed.fragment
                    ):
                        raise ValueError("Untrusted origin.")
                elif headers.get("sec-fetch-site") not in {"same-origin", "none"}:
                    # CLI clients must opt in with a non-simple header. A cross-site form cannot
                    # set it.
                    if headers.get("sec-fetch-site") or not (
                        headers.get("x-fragment") == "1"
                        or headers.get("x-promptlibrary-client") == "1"
                    ):
                        raise ValueError(
                            "Origin or X-PromptLibrary-Client: 1 is required for writes."
                        )
            except ValueError:
                await reject("Cross-origin writes are not allowed.", 403)
                return

        try:
            declared_length = int(headers.get("content-length", "0"))
        except ValueError:
            await reject("Invalid content length.", 400)
            return
        limit = self.settings.max_request_bytes
        if declared_length < 0 or declared_length > limit:
            await reject("Request exceeds the configured size limit.", 413)
            return

        # Buffer once, within a strict cap, so a framework body parser cannot turn an
        # oversized chunked request into a 500 or start a write before its size is known.
        chunks: list[bytes] = []
        received = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            received += len(chunk)
            if received > limit:
                await reject("Request exceeds the configured size limit.", 413)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def buffered_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, secure_send)
