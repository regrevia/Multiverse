from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


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
            limit=200_000,
        )

    def fetch_artifact_content(self, execution_ref: str, artifact_id: str) -> bytes:
        return self._read(
            "GET",
            f"/v1/executions/{_segment(execution_ref)}/artifacts/{_artifact_segment(artifact_id)}/content",
            operation="artifact_content",
            limit=1_048_576,
            binary=True,
        )

    def download_artifacts(
        self,
        execution_ref: str,
        namespace: str,
        observed: Any,
    ) -> list[tuple[dict[str, Any], bytes]]:
        validate_artifact_metadata(observed, execution_ref, namespace)
        response = self.fetch_artifacts(execution_ref)
        if (
            set(response) != {"executionRef", "namespace", "artifacts"}
            or response["executionRef"] != execution_ref
            or response["namespace"] != namespace
        ):
            raise HttpJobProtocolError("artifact metadata identity mismatch")
        metadata = response["artifacts"]
        validate_artifact_metadata(metadata, execution_ref, namespace)
        if metadata != observed:
            raise HttpJobProtocolError("artifact metadata differs from observation")
        downloaded = []
        for item in metadata:
            content = self.fetch_artifact_content(execution_ref, item["artifactId"])
            validate_artifact_content(item, content)
            downloaded.append((item, content))
        return downloaded

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        operation: str,
        limit: int | None = None,
    ) -> dict[str, Any]:
        body = self._read(
            method,
            path,
            payload=payload,
            operation=operation,
            limit=limit or self.max_response_bytes,
        )
        try:
            decoded = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HttpJobProtocolError("HTTP Job response is not JSON") from exc
        if not isinstance(decoded, dict):
            raise HttpJobProtocolError("HTTP Job response must be a JSON object")
        return decoded

    def _read(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        limit: int,
        payload: dict[str, Any] | None = None,
        binary: bool = False,
    ) -> bytes:
        encoded = None
        headers = {"Accept": "application/octet-stream" if binary else "application/json"}
        if payload is not None:
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=encoded, headers=headers, method=method)
        try:
            with build_opener(_NoRedirect()).open(
                request, timeout=self.timeout_seconds
            ) as response:
                if binary and response.headers.get_content_type() != "application/octet-stream":
                    raise HttpJobProtocolError("artifact content must be application/octet-stream")
                body = response.read(limit + 1)
        except HTTPError as exc:
            if operation == "submit":
                raise HttpJobTransportError("submit result is unknown") from exc
            if 300 <= exc.code < 400:
                raise HttpJobProtocolError("HTTP Job redirects are forbidden") from exc
            raise HttpJobError(f"HTTP Job {operation} failed with status {exc.code}") from exc
        except (URLError, TimeoutError, OSError, HTTPException) as exc:
            if operation == "submit":
                raise HttpJobTransportError("submit result is unknown") from exc
            raise HttpJobTransportError(f"HTTP Job {operation} transport failed") from exc
        if len(body) > limit:
            raise HttpJobProtocolError("HTTP Job response exceeds configured size limit")
        return bytes(body)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _segment(value: str) -> str:
    """Encode a generic execution identity without imposing the host's blob ID format."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or value.strip() in {".", ".."}
        or any(character in value for character in "/\\?#%")
        or any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value)
    ):
        raise HttpJobProtocolError("execution reference must be a safe opaque path segment")
    # Preserve legacy RFC 3986 pchar identities (including colon); encode Unicode/spaces.
    # Reject pre-encoded input above so repeated decoding cannot introduce delimiters.
    try:
        return quote(value, safe=":@!$&'()*+,;=-._~", encoding="utf-8", errors="strict")
    except UnicodeError as exc:
        raise HttpJobProtocolError("execution reference is not valid Unicode") from exc


def _artifact_segment(value: str) -> str:
    if (
        not isinstance(value, str)
        or value in {".", ".."}
        or re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,199}", value) is None
    ):
        raise HttpJobProtocolError("reference must be a safe opaque path segment")
    return value


def validate_artifact_metadata(items: Any, execution_ref: str, namespace: str) -> None:
    _segment(execution_ref)
    if not isinstance(items, list) or len(items) > 8:
        raise HttpJobProtocolError("artifacts must be an array of at most eight items")
    if len(json.dumps(items, ensure_ascii=False).encode("utf-8")) > 200_000:
        raise HttpJobProtocolError("artifact metadata exceeds size limit")
    identities = set()
    total = 0
    for item in items:
        if not isinstance(item, dict) or set(item) != {
            "artifactId",
            "version",
            "executionRef",
            "namespace",
            "name",
            "mediaType",
            "sizeBytes",
            "digest",
        }:
            raise HttpJobProtocolError("invalid artifact metadata fields")
        artifact_id = _artifact_segment(item["artifactId"])
        if artifact_id in identities:
            raise HttpJobProtocolError("duplicate artifact identity")
        identities.add(artifact_id)
        if (
            type(item["version"]) is not int
            or item["version"] != 1
            or item["executionRef"] != execution_ref
            or item["namespace"] != namespace
        ):
            raise HttpJobProtocolError("artifact version or identity mismatch")
        if type(item["sizeBytes"]) is not int or not 0 <= item["sizeBytes"] <= 1_048_576:
            raise HttpJobProtocolError("invalid artifact size")
        total += item["sizeBytes"]
        for field in ("name", "mediaType"):
            if (
                not isinstance(item[field], str)
                or not item[field].strip()
                or len(item[field]) > 1024
                or any(ord(c) < 32 for c in item[field])
            ):
                raise HttpJobProtocolError("invalid artifact name or media type")
        if (
            not isinstance(item["digest"], str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", item["digest"]) is None
        ):
            raise HttpJobProtocolError("invalid artifact digest")
    if total > 4_194_304:
        raise HttpJobProtocolError("artifact batch exceeds size limit")


def validate_artifact_content(metadata: dict[str, Any], content: bytes) -> None:
    if (
        len(content) != metadata["sizeBytes"]
        or "sha256:" + hashlib.sha256(content).hexdigest() != metadata["digest"]
    ):
        raise HttpJobProtocolError("artifact content size or digest mismatch")
