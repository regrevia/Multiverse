from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from multiverse_workflow.execution_host.backend import ProcessConfig
from multiverse_workflow.execution_host.service import ExecutionHost, create_server
from multiverse_workflow.execution_host.store import canonical, digest
from multiverse_workflow.runtime.http_job import HttpJobClient


def execution_request(key: str = "dispatch-1") -> dict[str, Any]:
    value = {"goal": "write a test deliverable"}
    return {
        "protocolVersion": "multiverse/v0.1",
        "dispatchKey": key,
        "effectKey": "invocation-1",
        "runId": "run-1",
        "scopeId": "scope-1",
        "invocationId": "invocation-1",
        "attemptId": "attempt-1",
        "attemptNo": 1,
        "executorRef": "example.execution-host.v1",
        "input": value,
        "inputDigest": digest(canonical(value).encode()),
        "inputSchemaDigest": "sha256:" + "b" * 64,
        "outputSchemaDigest": "sha256:" + "c" * 64,
        "deadlineAt": "2099-01-01T00:00:00Z",
        "authorizationRef": "trusted-local",
        "context": {"artifactRefs": [], "handoff": None, "promptRefs": [], "skillRefs": []},
        "traceContext": None,
    }


def wait_final(client: HttpJobClient, ref: str) -> dict[str, Any]:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        observation = client.observe(ref)
        if observation["executionFinal"]:
            return observation
        time.sleep(0.02)
    raise AssertionError("execution did not reach a terminal observation")


@pytest.fixture
def host_factory(tmp_path: Path) -> Iterator[Callable[..., tuple[ExecutionHost, HttpJobClient]]]:
    instances = []

    def create(script: str, **options: Any) -> tuple[ExecutionHost, HttpJobClient]:
        directory = tmp_path / str(len(instances))
        directory.mkdir()
        program = directory / "job.py"
        program.write_text(script)
        hook = options.pop("hook", None)
        config = ProcessConfig((sys.executable, str(program)), **options)
        host = ExecutionHost(directory / "host.db", directory / "jobs", config, hook=hook)
        server = create_server(host)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        instances.append((host, server, thread))
        return host, HttpJobClient(f"http://127.0.0.1:{server.server_port}", timeout_seconds=2)

    yield create
    for host, server, thread in reversed(instances):
        server.shutdown()
        server.server_close()
        thread.join()
        host.close()
