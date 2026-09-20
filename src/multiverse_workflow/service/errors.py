from __future__ import annotations

from typing import Any


class ServiceError(RuntimeError):
    """A stable service-facing error with a machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def not_found(message: str) -> ServiceError:
    return ServiceError("NOT_FOUND", message, status_code=404)


def state_conflict(message: str) -> ServiceError:
    return ServiceError("STATE_CONFLICT", message, status_code=409)
