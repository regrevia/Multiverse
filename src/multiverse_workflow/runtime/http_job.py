from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HttpJobError(RuntimeError):
    """The HTTP Job returned a protocol-level error."""


class HttpJobTransportError(HttpJobError):
    """The result of an HTTP Job operation cannot be known safely."""


class HttpJobProtocolError(HttpJobError):
    """The HTTP Job response violates the standard contract."""


@dataclass(frozen=True)
class HttpJobClient:
    """Small standard-library client for the Multiverse HTTP Job contract."""

    base_url: str
    timeout_seconds: float = 30.0
    max_response_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        normalized = self.base_url.rstrip("/")
        if not normalized:
            raise ValueError("HTTP Job base URL is required")
        if self.timeout_seconds <= 0:
            raise ValueError("HTTP Job timeout must be positive")
        if self.max_response_bytes < 1:
            raise ValueError("HTTP Job response limit must be positive")
        object.__setattr__(self, "base_url", normalized)

    def describe(self) -> dict[str, Any]:
        return self._request("GET", "/v1/descriptor", operation="descriptor")

    def submit(self, execution_request: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._request(
                "POST",
                "/v1/executions",
                payload=execution_request,
                operation="submit",
            )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise HttpJobTransportError("submit result is unknown") from exc
        execution_ref = response.get("executionRef")
        if not isinstance(execution_ref, str) or not execution_ref.strip():
            raise HttpJobProtocolError("submit response has no executionRef")
        return response

    def lookup(self, dispatch_key: str) -> dict[str, Any]:
        if not dispatch_key.strip():
            raise ValueError("dispatch key is required")
        return self._request(
            "GET",
            "/v1/executions/lookup?" + urlencode({"dispatchKey": dispatch_key}),
            operation="lookup",
        )

    def observe(self, execution_ref: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/executions/{_segment(execution_ref)}",
            operation="observe",
        )

    def cancel(self, execution_ref: str, command_id: str) -> dict[str, Any]:
        if not command_id.strip():
            raise ValueError("cancel command id is required")
        return self._request(
            "POST",
            f"/v1/executions/{_segment(execution_ref)}/cancel",
            payload={"commandId": command_id},
            operation="cancel",
        )

    def fetch_artifacts(self, execution_ref: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/executions/{_segment(execution_ref)}/artifacts",
            operation="fetch_artifacts",
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        operation: str,
    ) -> dict[str, Any]:
        encoded = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=encoded, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(self.max_response_bytes + 1)
        except HTTPError as exc:
            if operation == "submit":
                raise HttpJobTransportError("submit result is unknown") from exc
            raise HttpJobError(f"HTTP Job {operation} failed with status {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            if operation == "submit":
                raise HttpJobTransportError("submit result is unknown") from exc
            raise HttpJobTransportError(f"HTTP Job {operation} transport failed") from exc
        if len(body) > self.max_response_bytes:
            raise HttpJobProtocolError("HTTP Job response exceeds configured size limit")
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HttpJobProtocolError("HTTP Job response is not JSON") from exc
        if not isinstance(decoded, dict):
            raise HttpJobProtocolError("HTTP Job response must be a JSON object")
        return decoded


def _segment(value: str) -> str:
    if not value.strip() or "/" in value or "?" in value or "#" in value:
        raise ValueError("execution reference must be a non-empty opaque path segment")
    return value
