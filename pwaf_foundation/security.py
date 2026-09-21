"""Protect local browser requests.

Exact authorities prevent unexpected Host access. Mutation requests additionally
require an approved Origin and the process-lifetime CSRF token.
"""

import ipaddress
import secrets
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.errors import error_response


class BrowserSecurity:
    """Apply host, origin, and CSRF checks to every HTTP mutation, including app routes."""

    def __init__(self, app: ASGIApp, config: RuntimeConfig) -> None:
        self.app, self.config = app, config
        self.authorities = {urlsplit(origin).netloc for origin in config.origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        rejection = None
        if self.config.lan_auth == "proxy":
            peer = (scope.get("client") or ("", 0))[0]
            try:
                local_peer = ipaddress.ip_address(peer).is_loopback
            except ValueError:
                local_peer = False
            token = headers.get("x-pwaf-proxy-token", "")
            identity = headers.get("x-pwaf-user", "")
            if (
                not local_peer
                or len(headers.getlist("x-pwaf-proxy-token")) != 1
                or not secrets.compare_digest(token.encode(), self.config.proxy_token.encode())
            ):
                rejection = error_response(
                    401, "unauthorized", "Authenticated proxy access is required."
                )
            elif len(headers.getlist("x-pwaf-user")) != 1 or identity not in self.config.lan_users:
                rejection = error_response(403, "forbidden", "This user is not authorized.")
            elif (
                scope["method"] not in {"GET", "HEAD", "OPTIONS"}
                and identity not in self.config.lan_operators
            ):
                rejection = error_response(403, "forbidden", "An operator account is required.")
            else:
                scope.setdefault("state", {})["identity"] = identity
                # HTTPS is asserted only by the authenticated, locally connected proxy.
                scope["scheme"] = "https"
        else:
            scope.setdefault("state", {})["identity"] = self.config.mode
        if rejection is None and (
            len(headers.getlist("host")) != 1 or headers.get("host") not in self.authorities
        ):
            rejection = error_response(400, "invalid_host", "Host is not allowed.")
        elif rejection is None and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            if (
                len(headers.getlist("origin")) != 1
                or headers.get("origin") not in self.config.origins
            ):
                rejection = error_response(403, "invalid_origin", "Origin is not allowed.")
            else:
                expected = getattr(scope["app"].state, "csrf_token", "")
                supplied = headers.get("x-csrf-token", "")
                if not expected or not secrets.compare_digest(supplied.encode(), expected.encode()):
                    rejection = error_response(
                        403, "csrf_failed", "A valid CSRF token is required."
                    )

        async def secured_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"same-origin"),
                    ]
                )
            await send(message)

        if rejection is not None:
            await rejection(scope, receive, secured_send)
        else:
            await self.app(scope, receive, secured_send)
