from __future__ import annotations

import json
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from multiverse_workflow.runtime.registry import ExecutorDescriptor, ExecutorRegistry
from multiverse_workflow.runtime.runner import RunError, Runner

ROOT = Path(__file__).parents[2]


class _RuntimeJobHandler(BaseHTTPRequestHandler):
    submit_count = 0
    observations: dict[str, dict[str, Any]] = {}
    requests: list[dict[str, Any]] = []
    created_dispatch_keys: set[str] = set()
    drop_submit_response = False
    create_execution = True
    reconcile_by_key = "strong"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        if self.path == "/v1/executions":
            self.__class__.submit_count += 1
            self.__class__.requests.append(payload)
            execution_ref = "remote-execution-1"
            if self.__class__.create_execution:
                self.__class__.created_dispatch_keys.add(payload["dispatchKey"])
                self.__class__.observations.setdefault(
                    execution_ref,
                    {
                        "executionRef": execution_ref,
                        "revision": 1,
                        "status": "running",
                        "observedAt": "2026-09-21T00:00:00Z",
                        "executionFinal": False,
                        "effectState": "possible",
                    },
                )
            if self.__class__.drop_submit_response:
                self.close_connection = True
                return
            self._json(201, {"executionRef": execution_ref, "status": "accepted"})
            return
        self._json(404, {"error": "not found"})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/v1/descriptor":
            self._json(
                200,
                {
                    "reconcileByKey": self.__class__.reconcile_by_key,
                    "submitDedup": "durable",
                },
            )
            return
        if parsed.path == "/v1/executions/lookup":
            dispatch_key = parse_qs(parsed.query)["dispatchKey"][0]
            if dispatch_key in self.__class__.created_dispatch_keys:
                self._json(
                    200,
                    {
                        "status": "found",
                        "executionRef": "remote-execution-1",
                        "dispatchKey": dispatch_key,
                    },
                )
                return
            self._json(200, {"status": "not_created", "dispatchKey": dispatch_key})
            return
        if parsed.path.startswith("/v1/executions/"):
            execution_ref = parsed.path.rsplit("/", 1)[-1]
            self._json(200, self.__class__.observations[execution_ref])
            return
        self._json(404, {"error": "not found"})


@pytest.fixture
def runtime_job_server() -> str:
    _RuntimeJobHandler.submit_count = 0
    _RuntimeJobHandler.observations = {}
    _RuntimeJobHandler.requests = []
    _RuntimeJobHandler.created_dispatch_keys = set()
    _RuntimeJobHandler.drop_submit_response = False
    _RuntimeJobHandler.create_execution = True
    _RuntimeJobHandler.reconcile_by_key = "strong"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RuntimeJobHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _registry() -> ExecutorRegistry:
    return ExecutorRegistry(
        [
            ExecutorDescriptor(
                executor_ref="example.remote-content.v1",
                adapter="http_job",
                capabilities=frozenset({"content.produce@1", "content.review@1"}),
                contract_version="multiverse/v0.1",
                executor_version="1.0.0",
                supports_cancel=True,
                supports_idempotency=True,
                supports_recovery_query=True,
                observability_level="boundary",
                permission_level="trusted_local",
                installed=True,
                available=True,
                verified=True,
            ),
            ExecutorDescriptor(
                executor_ref="builtin.nonempty-deliverable.v1",
                adapter="builtin",
                capabilities=frozenset({"data.validate@1"}),
                contract_version="multiverse/v0.1",
                executor_version="1.0.0",
                supports_cancel=True,
                supports_idempotency=True,
                supports_recovery_query=True,
                observability_level="structured",
                permission_level="enforced",
                installed=True,
                available=True,
                verified=True,
            ),
            ExecutorDescriptor(
                executor_ref="builtin.human-review.v1",
                adapter="human",
                capabilities=frozenset({"human.review@1"}),
                contract_version="multiverse/v0.1",
                executor_version="1.0.0",
                supports_cancel=True,
                supports_idempotency=True,
                supports_recovery_query=True,
                observability_level="structured",
                permission_level="enforced",
                installed=True,
                available=True,
                verified=True,
            ),
        ]
    )


def _remote_package(tmp_path: Path, base_url: str) -> tuple[Path, Path]:
    package = tmp_path / "content-remote"
    shutil.copytree(ROOT / "presets/content-delivery", package)
    binding = tmp_path / "content-remote.yaml"
    text = (ROOT / "examples/bindings/content-remote.yaml").read_text(encoding="utf-8")
    config = f"config:\n        baseUrl: {base_url}\n        timeoutSeconds: 2"
    text = text.replace("config: {}", config, 1)
    text = text.replace("config: {}", config, 1)
    binding.write_text(text, encoding="utf-8")
    return package, binding


def test_http_job_worker_submits_observes_and_resumes_the_same_attempt(
    tmp_path: Path,
    runtime_job_server: str,
) -> None:
    package, binding = _remote_package(tmp_path, runtime_job_server)
    runner = Runner(
        package,
        binding_path=binding,
        database_path=tmp_path / "runtime.db",
        executor_registry=_registry(),
    )

    started = runner.start({"goal": "write a release note"})
    assert started["status"] == "running"
    attempt = runner.ledger.list_attempts(started["id"])[0]
    submit_wait = runner.ledger.get_wait_by_key("local", f"submit:{attempt['id']}")
    assert submit_wait is not None

    runner.sweep(worker_id="http-worker")
    assert _RuntimeJobHandler.submit_count == 1
    assert runner.ledger.get_attempt(attempt["id"])["external_ref"] == (
        "remote-execution-1"
    )

    runner.sweep(worker_id="http-worker")
    assert runner.ledger.get_attempt(attempt["id"])["status"] == "submitted"

    _RuntimeJobHandler.observations["remote-execution-1"] = {
        "executionRef": "remote-execution-1",
        "revision": 2,
        "status": "succeeded",
        "observedAt": "2026-09-21T00:00:02Z",
        "executionFinal": True,
        "effectState": "confirmed",
        "output": {"text": "Remote deliverable", "artifact_refs": []},
    }
    runner.sweep(worker_id="http-worker")

    assert _RuntimeJobHandler.submit_count == 1
    assert runner.ledger.get_attempt(attempt["id"])["status"] == "succeeded"
    assert runner.ledger.get_run(started["id"])["status"] == "running"
    assert {item["node_id"] for item in runner.ledger.list_invocations(started["id"])} >= {
        "produce",
    }


def test_http_job_unknown_submit_looks_up_the_same_execution_without_resubmitting(
    tmp_path: Path,
    runtime_job_server: str,
) -> None:
    package, binding = _remote_package(tmp_path, runtime_job_server)
    _RuntimeJobHandler.drop_submit_response = True
    runner = Runner(
        package,
        binding_path=binding,
        database_path=tmp_path / "runtime.db",
        executor_registry=_registry(),
    )

    started = runner.start({"goal": "write a release note"})
    attempt = runner.ledger.list_attempts(started["id"])[0]

    runner.sweep(worker_id="http-worker")

    outbox = runner.ledger.get_submit_outbox(attempt["id"])
    recovered = runner.ledger.get_attempt(attempt["id"])
    assert _RuntimeJobHandler.submit_count == 1
    assert outbox is not None
    assert outbox["status"] == "submitted"
    assert outbox["external_ref"] == "remote-execution-1"
    assert recovered is not None
    assert recovered["external_ref"] == "remote-execution-1"
    assert recovered["status"] == "submitted"


def test_http_job_unknown_submit_does_not_retry_without_strong_lookup_proof(
    tmp_path: Path,
    runtime_job_server: str,
) -> None:
    package, binding = _remote_package(tmp_path, runtime_job_server)
    _RuntimeJobHandler.drop_submit_response = True
    _RuntimeJobHandler.create_execution = False
    _RuntimeJobHandler.reconcile_by_key = "eventual"
    runner = Runner(
        package,
        binding_path=binding,
        database_path=tmp_path / "runtime.db",
        executor_registry=_registry(),
    )

    started = runner.start({"goal": "write a release note"})
    attempt = runner.ledger.list_attempts(started["id"])[0]

    with pytest.raises(RunError, match="strong lookup"):
        runner.sweep(worker_id="http-worker")

    outbox = runner.ledger.get_submit_outbox(attempt["id"])
    assert _RuntimeJobHandler.submit_count == 1
    assert outbox is not None
    assert outbox["status"] == "unknown"
