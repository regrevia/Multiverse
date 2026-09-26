from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from multiverse_workflow.api.dependencies import ServiceSettings
from multiverse_workflow.cli.main import app
from multiverse_workflow.runtime.catalog import CatalogError
from multiverse_workflow.runtime.registry import local_executor_registry
from multiverse_workflow.runtime.runner import RunError

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "presets/content-delivery"
LOCAL = ROOT / "examples/bindings/content-local.yaml"


def _catalog(path: Path, *, remote: bool = False) -> Path:
    path.mkdir(exist_ok=True)
    schema = b'{"type":"object"}'
    (path / "config.json").write_bytes(schema)
    entries = []
    for descriptor in local_executor_registry().descriptors():
        entry = descriptor.as_catalog_entry()
        entry.pop("declared")
        entry.pop("configSchema")
        entry.pop("verificationEvidence")
        entry.pop("effectiveConfigSchemaDigest", None)
        if remote and entry["executorRef"] == "example.remote-content.v1":
            entry.update(installed=True, available=True, verified=True)
        entry.update(
            configSchemaRef="config.json",
            configSchemaDigest="sha256:" + hashlib.sha256(schema).hexdigest(),
        )
        if entry["verified"]:
            entry["verificationEvidence"] = {
                "kind": "operator-attestation",
                "reference": "local-test-review-1",
                "environment": "test-loopback",
                "executorVersion": entry["executorVersion"],
                "cases": ["contract"],
            }
        entries.append(entry)
    (path / "executor-registration.json").write_text(
        json.dumps(
            {
                "catalogVersion": "multiverse.executor-catalog/v0.1",
                "executors": entries,
            }
        )
    )
    return path


def test_capabilities_executor_schema_and_unknown_reference(tmp_path: Path) -> None:
    registry = _catalog(tmp_path / "catalog")
    cli = CliRunner()
    result = cli.invoke(
        app,
        ["capabilities", "--registry", str(registry), "--executor", "local.process.v1", "--json"],
    )
    assert result.exit_code == 0, result.output
    entries = json.loads(result.stdout)["executors"]
    assert len(entries) == 1
    assert entries[0]["configSchema"]
    assert entries[0]["configSchemaDigest"].startswith("sha256:")
    result = cli.invoke(app, ["capabilities", "--executor", "missing", "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["code"] == "EXECUTOR_UNRESOLVED"


@pytest.mark.parametrize(
    "command",
    [
        "validate",
        "preflight",
        "run",
        "worker",
        "sweep",
        "resume",
        "rerun",
        "decide",
        "capabilities",
    ],
)
def test_missing_catalog_is_structured_failure_before_runtime(
    tmp_path: Path,
    command: str,
) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text('{"goal":"write a note"}')
    arguments = {
        "validate": [str(PACKAGE), "--binding", str(LOCAL)],
        "preflight": [str(PACKAGE), "--binding", str(LOCAL)],
        "run": [str(PACKAGE), "--binding", str(LOCAL), "--input", str(input_path)],
        "worker": [str(PACKAGE), "--binding", str(LOCAL), "--once"],
        "sweep": [str(PACKAGE), "--binding", str(LOCAL), "--worker-id", "test"],
        "resume": [
            "run_missing",
            "--package",
            str(PACKAGE),
            "--binding",
            str(LOCAL),
            "--expected-version",
            "1",
            "--reason",
            "test",
        ],
        "rerun": [
            "run_missing",
            "--package",
            str(PACKAGE),
            "--binding",
            str(LOCAL),
            "--reason",
            "test",
        ],
        "decide": [
            "request_missing",
            str(PACKAGE),
            "--binding",
            str(LOCAL),
            "--subject-digest",
            "sha256:test",
            "--expected-version",
            "1",
        ],
        "capabilities": [],
    }[command]
    result = CliRunner().invoke(
        app, [command, *arguments, "--registry", str(tmp_path / "missing"), "--json"]
    )
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["code"] == "CATALOG_INVALID"


def test_old_binding_with_explicit_catalog_and_stable_settings_snapshot(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path / "catalog")
    for command in ("validate", "preflight"):
        result = CliRunner().invoke(
            app,
            [command, str(PACKAGE), "--binding", str(LOCAL), "--registry", str(catalog), "--json"],
        )
        assert result.exit_code == 0, result.output
    settings = ServiceSettings(
        package_dir=PACKAGE,
        binding_path=LOCAL,
        database_path=tmp_path / "runtime.db",
        registry_path=catalog,
        bearer_token="test-token",
    )
    (catalog / "executor-registration.json").unlink()
    application = settings.create_application()
    worker = settings.create_worker(worker_id="snapshot-test")
    try:
        assert (
            application.runner._executor_registry.capability_catalog()
            == worker.runner._executor_registry.capability_catalog()
        )
        assert worker.run_once() == []
        with pytest.raises(RunError, match="EXECUTOR_CATALOG_REVOKED"):
            application.runner.start({"goal": "must not run after revocation"})
        with pytest.raises(CatalogError):
            ServiceSettings(
                package_dir=PACKAGE,
                binding_path=LOCAL,
                database_path=tmp_path / "other.db",
                registry_path=catalog,
                bearer_token="test-token",
            )
    finally:
        application.close()
        worker.close()


class _JobHandler(BaseHTTPRequestHandler):
    submissions: list[dict[str, Any]] = []

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _json(self, status: int, value: dict[str, Any]) -> None:
        content = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.submissions.append(payload)
        self._json(201, {"executionRef": "fixture-job-1", "status": "accepted"})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/descriptor":
            self._json(200, {"reconcileByKey": "strong", "submitDedup": "durable"})
        else:
            self._json(
                200,
                {
                    "executionRef": "fixture-job-1",
                    "revision": 1,
                    "status": "succeeded",
                    "observedAt": "2026-09-26T00:00:00Z",
                    "executionFinal": True,
                    "effectState": "confirmed",
                    "output": {"text": "Local HTTP fixture", "artifact_refs": []},
                },
            )


@pytest.mark.anyio
async def test_cli_serve_api_and_cli_worker_use_custom_http_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn

    _JobHandler.submissions = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _JobHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    registry = _catalog(tmp_path / "catalog", remote=True)
    text = (ROOT / "examples/bindings/content-remote.yaml").read_text()
    config = (
        f"config:\n        baseUrl: http://127.0.0.1:{server.server_port}"
        "\n        timeoutSeconds: 2"
    )
    text = text.replace("config: {}", config, 2)
    binding = tmp_path / "binding.yaml"
    binding.write_text(text)
    database = tmp_path / "runtime.db"
    apps: list[Any] = []
    monkeypatch.setattr(uvicorn, "run", lambda application, **kwargs: apps.append(application))
    try:
        result = CliRunner().invoke(
            app,
            [
                "serve",
                "--package",
                str(PACKAGE),
                "--binding",
                str(binding),
                "--db",
                str(database),
                "--registry",
                str(registry),
                "--bearer-token",
                "test-token",
            ],
        )
        assert result.exit_code == 0, result.output
        api = apps[0]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/namespaces/local/runs",
                headers={"Authorization": "Bearer test-token", "Idempotency-Key": "http-run"},
                json={
                    "deploymentId": "deployment_local",
                    "workflowId": "delivery",
                    "input": {"goal": "write a note"},
                },
            )
            assert response.status_code == 202, response.text
            run_id = response.json()["resourceId"]
        for _ in range(3):
            result = CliRunner().invoke(
                app,
                [
                    "worker",
                    str(PACKAGE),
                    "--binding",
                    str(binding),
                    "--db",
                    str(database),
                    "--registry",
                    str(registry),
                    "--once",
                    "--json",
                ],
            )
            assert result.exit_code == 0, result.output
        assert _JobHandler.submissions
        attempts = api.state.runtime.runner.ledger.list_attempts(run_id)
        remote_attempts = [a for a in attempts if a["observation_json"] is not None]
        assert remote_attempts
        assert remote_attempts[0]["status"] == "succeeded"
        assert json.loads(remote_attempts[0]["observation_json"])["executionRef"] == "fixture-job-1"
        assert json.loads(remote_attempts[0]["output_json"])["text"] == "Local HTTP fixture"
        assert _JobHandler.submissions[0]["dispatchKey"] == remote_attempts[0]["dispatch_key"]
        input_file = tmp_path / "input.json"
        input_file.write_text('{"goal":"CLI custom registry run"}')
        direct_run = CliRunner().invoke(
            app,
            [
                "run",
                str(PACKAGE),
                "--binding",
                str(binding),
                "--registry",
                str(registry),
                "--input",
                str(input_file),
                "--db",
                str(tmp_path / "cli.db"),
                "--json",
            ],
        )
        assert direct_run.exit_code == 0, direct_run.output
        assert json.loads(direct_run.stdout)["status"] == "running"
        api.state.runtime.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("first", ["compiler.preflight", "runtime"])
def test_public_runtime_imports_are_independent_of_import_order(first: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import multiverse_workflow.{first}; "
            "from multiverse_workflow.runtime import "
            "Ledger, LedgerConflict, LocalWorker, WorkerLockError; "
            "assert all((Ledger, LedgerConflict, LocalWorker, WorkerLockError))",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_missing_serve_catalog_does_not_create_token_or_database(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "serve",
            "--package",
            str(PACKAGE),
            "--binding",
            str(LOCAL),
            "--db",
            str(tmp_path / "runtime.db"),
            "--registry",
            str(tmp_path / "missing"),
        ],
    )
    assert result.exit_code == 2
    assert list(tmp_path.iterdir()) == []
