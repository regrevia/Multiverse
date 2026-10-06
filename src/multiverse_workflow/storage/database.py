from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse


class DatabaseTargetError(ValueError):
    """A database target is unsupported or ambiguous."""


@dataclass(frozen=True)
class DatabaseTarget:
    """The immutable storage target selected by a deployment."""

    backend: str
    location: str
    service_mode: bool

    @property
    def safe_location(self) -> str:
        """Return a diagnostic-safe location without a database password."""
        if self.backend != "postgresql":
            return self.location
        parsed = urlparse(self.location)
        if parsed.password is None:
            userinfo = parsed.netloc
        else:
            userinfo = None
        user = parsed.username or ""
        host = parsed.hostname or ""
        try:
            port = f":{parsed.port}" if parsed.port else ""
        except ValueError:
            port = ""
        if userinfo is None:
            auth = f"{user}:***@" if user else "***@"
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            netloc = f"{auth}{host}{port}"
        else:
            netloc = parsed.netloc
        sensitive_query_keys = {
            "password",
            "passwd",
            "pwd",
            "token",
            "secret",
            "api_key",
            "access_token",
            "credential",
            "credentials",
        }
        query = [
            (
                key,
                "***"
                if (
                    key.lower() in sensitive_query_keys
                    or any(
                        marker in key.lower()
                        for marker in ("token", "secret", "password", "key")
                    )
                )
                else value,
            )
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        return parsed._replace(netloc=netloc, query=urlencode(query)).geturl()


def parse_database_target(value: Path | str) -> DatabaseTarget:
    """Parse the explicit SQLite or PostgreSQL deployment target.

    SQLite remains the personal/local backend. PostgreSQL is a service target;
    this function only validates and classifies the target and never connects.
    """
    if isinstance(value, Path):
        location = str(value.expanduser().resolve())
        if not location:
            raise DatabaseTargetError("SQLite database path must not be empty")
        return DatabaseTarget(backend="sqlite", location=location, service_mode=False)
    if not isinstance(value, str) or not value.strip():
        raise DatabaseTargetError("database target must not be empty")
    raw = value.strip()
    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise DatabaseTargetError("invalid database target URL") from exc
    if parsed.scheme in {"postgresql", "postgresql+psycopg"}:
        if not parsed.netloc or not parsed.path or parsed.path == "/":
            raise DatabaseTargetError("PostgreSQL target must include host and database")
        try:
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise DatabaseTargetError("PostgreSQL target contains an invalid port") from exc
        if hostname is None:
            raise DatabaseTargetError("PostgreSQL target must include a valid host")
        if port is not None and not 0 <= port <= 65535:
            raise DatabaseTargetError("PostgreSQL target contains an invalid port")
        return DatabaseTarget(backend="postgresql", location=raw, service_mode=True)
    if parsed.scheme:
        raise DatabaseTargetError(f"unsupported database backend: {parsed.scheme}")
    raise DatabaseTargetError(
        "string database targets must use an explicit PostgreSQL URL; use Path for SQLite"
    )
