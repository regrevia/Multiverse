from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import pytest

from multiverse_workflow.runtime.http_job import (
    HttpJobClient,
    HttpJobProtocolError,
    HttpJobTransportError,
)


class _JobHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict[str, Any] | None]] = []
    executions: dict[str, dict[str, Any]] = {}
    fail_submit = False
    execution_ref: str | None = None

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        self.requests.append(("GET", self.path, None))
        if parsed.path == "/v1/descriptor":
            self._json(
                200,
                {
                    "executorRef": "test.http-job.v1",
                    "adapter": "http_job",
                    "adapterVersion": "1.0.0",
                    "executorVersion": "1.0.0",
                    "contractVersion": "multiverse/v0.1",
                    "capabilities": ["content.produce@1"],
                    "cancelMode": "confirmed",
                    "submitDedup": "durable",
                    "reconcileByKey": "strong",
                    "retryOwner": "runtime",
                    "observability": "boundary",
                    "enforcement": "trusted_local",
                },
            )
            return
        if parsed.path == "/v1/executions/lookup":
            key = parse_qs(parsed.query)["dispatchKey"][0]
            for execution in self.executions.values():
                if execution["dispatchKey"] == key:
                    self._json(200, {"status": "found", **execution})
                    return
            self._json(200, {"status": "not_created", "dispatchKey": key})
            return
        if parsed.path.startswith("/v1/executions/"):
            execution_id = unquote(parsed.path.rsplit("/", 1)[-1])
            execution = self.executions[execution_id]
            self._json(200, execution["observation"])
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        self.requests.append(("POST", self.path, payload))
        if self.path == "/v1/executions":
            if self.fail_submit:
                self.close_connection = True
                return
            dispatch_key = payload["dispatchKey"]
            for execution_id, execution in self.executions.items():
                if execution["dispatchKey"] == dispatch_key:
                    self._json(200, {"executionRef": execution_id, "status": "accepted"})
                    return
            execution_id = self.execution_ref or f"exec-{len(self.executions) + 1}"
            self.executions[execution_id] = {
                "executionRef": execution_id,
                "dispatchKey": dispatch_key,
                "request": payload,
                "observation": {
                    "executionRef": execution_id,
                    "revision": 1,
                    "status": "running",
                    "observedAt": "2026-09-21T00:00:00Z",
                    "executionFinal": False,
                    "effectState": "possible",
                },
            }
            self._json(201, {"executionRef": execution_id, "status": "accepted"})
            return
        if self.path.startswith("/v1/executions/") and self.path.endswith("/cancel"):
            execution_id = unquote(self.path.removesuffix("/cancel").rsplit("/", 1)[-1])
            assert execution_id in self.executions
            self._json(202, {"status": "accepted"})
            return
        self._json(404, {"error": "not found"})


@pytest.fixture
def job_server() -> str:
    _JobHandler.requests = []
    _JobHandler.executions = {}
    _JobHandler.fail_submit = False
    _JobHandler.execution_ref = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _JobHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _request() -> dict[str, Any]:
    return {
        "protocolVersion": "multiverse/v0.1",
        "dispatchKey": "attempt-1:1",
        "effectKey": "invocation-1",
        "runId": "run-1",
        "scopeId": "scope-1",
        "invocationId": "invocation-1",
        "attemptId": "attempt-1",
        "attemptNo": 1,
        "executorRef": "test.http-job.v1",
        "input": {"goal": "write"},
        "inputDigest": "sha256:" + "a" * 64,
        "inputSchemaDigest": "sha256:" + "b" * 64,
        "outputSchemaDigest": "sha256:" + "c" * 64,
        "deadlineAt": "2026-09-22T00:00:00Z",
        "authorizationRef": "grant-1",
        "context": {"artifactRefs": [], "handoff": None, "promptRefs": [], "skillRefs": []},
        "traceContext": None,
    }


def test_http_job_client_supports_standard_lifecycle_and_deduplicates_submit(
    job_server: str,
) -> None:
    client = HttpJobClient(job_server, timeout_seconds=2)

    descriptor = client.describe()
    first = client.submit(_request())
    duplicate = client.submit(_request())
    lookup = client.lookup("attempt-1:1")
    observation = client.observe(first["executionRef"])
    cancelled = client.cancel(first["executionRef"], "cancel-1")

    assert descriptor["reconcileByKey"] == "strong"
    assert first["executionRef"] == duplicate["executionRef"]
    assert lookup["status"] == "found"
    assert observation["status"] == "running"
    assert cancelled["status"] == "accepted"
    submits = [item for item in _JobHandler.requests if item[1] == "/v1/executions"]
    assert len(submits) == 2
    assert submits[0][2] == submits[1][2]


def test_http_job_client_reports_transport_uncertainty_without_retrying_submit(
    job_server: str,
) -> None:
    _JobHandler.fail_submit = True
    client = HttpJobClient(job_server, timeout_seconds=1)

    with pytest.raises(HttpJobTransportError, match="submit result is unknown"):
        client.submit(_request())


@pytest.mark.parametrize("execution_ref", ["job:123", "job:" + "x" * 300, "job:任务 123"])
def test_legacy_no_artifact_execution_references_complete_real_http_lifecycle(
    job_server: str,
    execution_ref: str,
) -> None:
    _JobHandler.execution_ref = execution_ref
    client = HttpJobClient(job_server, timeout_seconds=2)
    accepted = client.submit(_request())
    assert accepted["executionRef"] == execution_ref
    assert client.observe(execution_ref)["executionRef"] == execution_ref
    assert client.cancel(execution_ref, "legacy-cancel")["status"] == "accepted"
    encoded = quote(execution_ref, safe=":@!$&'()*+,;=-._~")
    assert [(method, path) for method, path, _ in _JobHandler.requests] == [
        ("POST", "/v1/executions"),
        ("GET", f"/v1/executions/{encoded}"),
        ("POST", f"/v1/executions/{encoded}/cancel"),
    ]


@pytest.mark.parametrize(
    "execution_ref",
    [
        "",
        " ",
        ".",
        "..",
        " .. ",
        "../other",
        "job/other",
        "job\\other",
        "job?query=1",
        "job#fragment",
        "%2e%2e",
        "job%2Fother",
        "%252e%252e",
        "job\x00",
        "job\r\nX-Injected: true",
        "job\x7f",
        "job\x85",
    ],
)
def test_unsafe_execution_references_are_rejected_before_any_http_request(
    job_server: str,
    execution_ref: str,
) -> None:
    client = HttpJobClient(job_server, timeout_seconds=2)
    operations = [
        lambda: client.observe(execution_ref),
        lambda: client.cancel(execution_ref, "cancel-dangerous"),
        lambda: client.fetch_artifacts(execution_ref),
        lambda: client.fetch_artifact_content(execution_ref, "safe-blob"),
    ]
    for operation in operations:
        with pytest.raises(HttpJobProtocolError, match="safe opaque path segment"):
            operation()
    assert not _JobHandler.requests


@pytest.mark.parametrize("artifact_id", ["blob:123", "x" * 201, "文件", "..", "%2e%2e"])
def test_blob_id_constraints_remain_strict_independently_of_execution_reference(
    job_server: str,
    artifact_id: str,
) -> None:
    client = HttpJobClient(job_server, timeout_seconds=2)
    with pytest.raises(HttpJobProtocolError, match="safe opaque path segment"):
        client.fetch_artifact_content("job:123", artifact_id)
    assert not _JobHandler.requests
