"""Exact loopback origin and ephemeral desktop-session request protection."""

import hmac
import re
import secrets
from dataclasses import dataclass, field

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


@dataclass(frozen=True)
class LocalSecurityConfig:
    port: int
    csrf_token: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)

    def __post_init__(self) -> None:
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("A literal loopback port is required")
        if not isinstance(self.csrf_token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", self.csrf_token):
            raise ValueError("A valid desktop-session token is required")

    @property
    def host(self) -> str:
        return f"127.0.0.1:{self.port}"

    @property
    def origin(self) -> str:
        return f"http://{self.host}"


class LocalRequestProtection:
    def __init__(self, app: ASGIApp, security: LocalSecurityConfig) -> None:
        self.app, self.security = app, security

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.getlist("origin")
        site = headers.getlist("sec-fetch-site")
        allowed = headers.getlist("host") == [self.security.host]
        allowed = allowed and (not origin or origin == [self.security.origin])
        navigation = site == ["none"] and scope["method"] in {"GET", "HEAD"} and scope["path"] != "/api/v1/desktop-session"
        allowed = allowed and (not site or site == ["same-origin"] or navigation)
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            tokens = headers.getlist("x-redpath-session")
            allowed = allowed and origin == [self.security.origin] and len(tokens) == 1
            allowed = allowed and hmac.compare_digest(tokens[0].encode(), self.security.csrf_token.encode())
        if scope["path"] == "/api/v1/desktop-session":
            # A custom header excludes navigations/forms. Cross-origin fetches
            # require a CORS preflight, which this application never grants.
            allowed = allowed and headers.getlist("x-redpath-bootstrap") == ["1"]
        if not allowed:
            await JSONResponse({"detail": "LOCAL_REQUEST_REJECTED"}, status_code=403, headers={"Cache-Control": "no-store"})(scope, receive, send)
            return
        await self.app(scope, receive, send)
