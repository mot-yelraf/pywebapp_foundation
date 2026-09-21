"""Validate local and LAN startup configuration.

LAN password authentication is opt-in. Direct LAN mode uses an explicit public
origin; authenticated LAN mode trusts only a same-machine HTTPS proxy.
"""

import ipaddress
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RuntimeConfig:
    """Immutable process configuration, independent of editable settings."""

    host: str = "127.0.0.1"
    port: int = 8191
    data_dir: Path = Path("data")
    log_level: str = "INFO"
    mode: str = "local"
    lan_auth: str = "none"
    public_origin: str = ""
    proxy_token_file: Path | None = None
    lan_users: frozenset[str] = frozenset()
    lan_operators: frozenset[str] = frozenset()
    proxy_token: str = field(default="", init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.mode not in {"local", "lan"} or self.lan_auth not in {"none", "proxy"}:
            raise ValueError("PWAF_MODE must be local/lan; PWAF_LAN_AUTH must be none/proxy")
        try:
            loopback = self.host == "localhost" or ipaddress.ip_address(self.host).is_loopback
        except ValueError as exc:
            raise ValueError("PWAF_HTTP_HOST must be localhost or an IP address") from exc
        if (self.mode == "local" or self.lan_auth == "proxy") and not loopback:
            raise ValueError("Local and authenticated proxy modes must bind to loopback")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("PWAF_HTTP_PORT must be an integer from 1 through 65535")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("PWAF_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        object.__setattr__(self, "data_dir", Path(self.data_dir).expanduser().resolve())
        if self.mode == "local":
            if self.public_origin or self.lan_auth != "none":
                raise ValueError("LAN configuration requires PWAF_MODE=lan")
        else:
            parsed = urlsplit(self.public_origin)
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError("Invalid PWAF_PUBLIC_ORIGIN port") from exc
            scheme = "https" if self.lan_auth == "proxy" else "http"
            if (
                parsed.scheme != scheme
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or (port is not None and port < 1)
                or not re.fullmatch(r"https?://[A-Za-z0-9.\[\]:-]+", self.public_origin)
            ):
                raise ValueError(
                    f"PWAF_PUBLIC_ORIGIN must be a {scheme.upper()} origin without a path"
                )
            if self.lan_auth == "none" and (port or 80) != self.port:
                raise ValueError("Direct LAN origin port must match PWAF_HTTP_PORT")
            hostname = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
            suffix = f":{port}" if port and port != (443 if scheme == "https" else 80) else ""
            object.__setattr__(self, "public_origin", f"{scheme}://{hostname}{suffix}")
        if self.lan_auth == "none":
            if self.proxy_token_file or self.lan_users or self.lan_operators:
                raise ValueError("Proxy credentials and users require PWAF_LAN_AUTH=proxy")
        else:
            if not self.lan_users or not self.lan_operators.issubset(self.lan_users):
                raise ValueError("LAN users are required; operators must be a subset of users")
            if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", user) for user in self.lan_users):
                raise ValueError(
                    "LAN usernames must use letters, digits, dots, underscores, or hyphens"
                )
            if self.proxy_token_file is None:
                raise ValueError("PWAF_PROXY_TOKEN_FILE is required for proxy authentication")
            try:
                token = Path(self.proxy_token_file).read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError) as exc:
                raise ValueError("Cannot read PWAF_PROXY_TOKEN_FILE") from exc
            if not re.fullmatch(r"[a-f0-9]{64}", token):
                raise ValueError("Proxy token must be 64 lowercase hexadecimal characters")
            object.__setattr__(self, "proxy_token", token)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "RuntimeConfig":
        """Parse supported variables without creating runtime files."""
        env = os.environ if environ is None else environ
        try:
            port = int(env.get("PWAF_HTTP_PORT", "8191"))
        except ValueError as exc:
            raise ValueError("PWAF_HTTP_PORT must be an integer from 1 through 65535") from exc
        directory = env.get("PWAF_DATA_DIR", "./data")
        if not directory.strip():
            raise ValueError("PWAF_DATA_DIR must not be empty")
        mode, auth = env.get("PWAF_MODE", "local"), env.get("PWAF_LAN_AUTH", "none")
        default_host = "0.0.0.0" if mode == "lan" and auth == "none" else "127.0.0.1"
        return cls(
            host=env.get("PWAF_HTTP_HOST", default_host),
            port=port,
            data_dir=Path(directory),
            log_level=env.get("PWAF_LOG_LEVEL", "INFO"),
            mode=mode,
            lan_auth=auth,
            public_origin=env.get("PWAF_PUBLIC_ORIGIN", ""),
            proxy_token_file=Path(env["PWAF_PROXY_TOKEN_FILE"])
            if env.get("PWAF_PROXY_TOKEN_FILE")
            else None,
            lan_users=frozenset(
                filter(None, (v.strip() for v in env.get("PWAF_LAN_USERS", "").split(",")))
            ),
            lan_operators=frozenset(
                filter(None, (v.strip() for v in env.get("PWAF_LAN_OPERATORS", "").split(",")))
            ),
        )

    @property
    def origins(self) -> frozenset[str]:
        """Return exact permitted browser origins, including the configured port."""
        if self.mode == "lan":
            return frozenset({self.public_origin})
        hosts = {self.host, "localhost", "127.0.0.1", "::1"}
        suffix = "" if self.port == 80 else f":{self.port}"
        return frozenset(
            f"http://{'[' + host + ']' if ':' in host else host}{suffix}" for host in hosts
        )
