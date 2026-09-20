from __future__ import annotations

import uuid
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
        retryable: bool = False,
        evidence_refs: list[str] | None = None,
        next_actions: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.retryable = retryable
        self.evidence_refs = evidence_refs or []
        self.next_actions = next_actions or []
        self.request_id = f"req_{uuid.uuid4().hex}"


def not_found(message: str) -> ServiceError:
    return ServiceError("NOT_FOUND", message, status_code=404)


def state_conflict(message: str) -> ServiceError:
    return ServiceError("STATE_CONFLICT", message, status_code=409)


def idempotency_conflict(message: str) -> ServiceError:
    return ServiceError("IDEMPOTENCY_CONFLICT", message, status_code=409)
