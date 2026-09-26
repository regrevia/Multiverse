"""Current executable compatibility boundaries, not future import/SDK certification."""

from __future__ import annotations

import asyncio
import json
import shutil
import tomllib
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from multiverse_workflow import __version__
from multiverse_workflow.api.app import create_app
from multiverse_workflow.api.dependencies import ServiceSettings
from multiverse_workflow.cli.main import app
from multiverse_workflow.compiler.compiler import compile_package
from multiverse_workflow.protocol.loader import load_document
from multiverse_workflow.protocol.models import BindingSet, Workflow, WorkflowPackage

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "presets/content-delivery"
BINDING = ROOT / "examples/bindings/content-local.yaml"


def test_software_versions_agree_without_changing_wire_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    inspector = json.loads((ROOT / "inspector/package.json").read_text())
    assert project["project"]["version"] == inspector["version"] == __version__
    cli = CliRunner().invoke(app, ["--version"])
    assert cli.exit_code == 0
    assert cli.stdout.strip() == __version__
    compiled = compile_package(PACKAGE, binding_path=BINDING)
    assert compiled.ok
    assert {plan.plan_version for plan in compiled.plans.values()} == {"multiverse/v0.1"}


@pytest.mark.parametrize(
    "resource,model",
    [
        (PACKAGE / "manifest.yaml", WorkflowPackage),
        (PACKAGE / "workflows/delivery.yaml", Workflow),
        (BINDING, BindingSet),
    ],
)
@pytest.mark.parametrize("version", ["multiverse/v1", "multiverse/v0.2", "multiverse/v9"])
def test_unknown_resource_versions_are_rejected_before_execution(
    resource: Path,
    model: type,
    version: str,
) -> None:
    value = load_document(resource).value
    model.model_validate(value)
    value["apiVersion"] = version
    with pytest.raises(ValidationError):
        model.model_validate(value)


def test_v01_package_compilation_is_read_only_and_not_an_import_claim(tmp_path: Path) -> None:
    package = tmp_path / "v01"
    shutil.copytree(PACKAGE, package)
    before = {
        str(path.relative_to(package)): path.read_bytes()
        for path in package.rglob("*")
        if path.is_file()
    }
    result = compile_package(package, binding_path=BINDING)
    assert result.ok
    after = {
        str(path.relative_to(package)): path.read_bytes()
        for path in package.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert sorted(path.name for path in tmp_path.iterdir()) == ["v01"]
    manifest = package / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace("multiverse/v0.1", "multiverse/v9"))
    rejected = compile_package(package, binding_path=BINDING)
    assert not rejected.ok
    assert rejected.plans == {}
    assert any(item.pointer == "/apiVersion" for item in rejected.diagnostics)


def test_preflight_cli_report_has_its_own_version() -> None:
    result = CliRunner().invoke(
        app,
        ["preflight", str(PACKAGE), "--binding", str(BINDING), "--json"],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["reportVersion"] == "multiverse.preflight/v0.1"


def test_api_unknown_version_and_fields_do_not_create_runs(tmp_path: Path) -> None:
    asyncio.run(_check_api_compatibility(tmp_path))


async def _check_api_compatibility(tmp_path: Path) -> None:
    application = create_app(
        ServiceSettings(
            database_path=tmp_path / "runtime.db",
            package_dir=PACKAGE,
            binding_path=BINDING,
            bearer_token="compatibility-test-token",
        )
    )
    headers = {"Authorization": "Bearer compatibility-test-token", "Idempotency-Key": "compat-v1"}
    request = {
        "deploymentId": "deployment_local",
        "workflowId": "delivery",
        "input": {"goal": "compatibility"},
    }
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/openapi.json")).json()["info"]["version"] == __version__
        unsupported = await client.post(
            "/api/v99/namespaces/local/runs", json=request, headers=headers
        )
        assert unsupported.status_code == 404
        invalid = await client.post(
            "/api/v1/namespaces/local/runs",
            json={**request, "unknownRequired": True},
            headers=headers,
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_ARGUMENT"
        assert application.state.runtime.runner.ledger.list_queued_runs() == []
        created = await client.post("/api/v1/namespaces/local/runs", json=request, headers=headers)
        assert created.status_code == 202
        run_id = created.json()["resourceId"]
        projection = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/graph", headers=headers
        )
        assert projection.json()["protocolVersion"] == "multiverse/v0.1"
    application.state.runtime.close()


@pytest.fixture
def compatibility_job_server() -> Iterator[
    tuple[str, dict[str, str], list[tuple[str, str, object]]]
]:
    payload = {"futureOptionalField": "retained"}
    seen: list[tuple[str, str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            seen.append((self.command, self.path, json.loads(self.rfile.read(length))))
            body = json.dumps(payload).encode("utf-8")
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", payload, seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("valid", [True, False])
def test_http_job_v1_response_extensions_do_not_replace_required_fields(
    compatibility_job_server: tuple[str, dict[str, str], list[tuple[str, str, object]]],
    valid: bool,
) -> None:
    from multiverse_workflow.runtime.http_job import HttpJobClient, HttpJobProtocolError

    base_url, payload, seen = compatibility_job_server
    if valid:
        payload["executionRef"] = "exec-compat"
    client = HttpJobClient(base_url, timeout_seconds=2)
    if valid:
        assert client.submit({"dispatchKey": "fixture"}) == payload
    else:
        with pytest.raises(HttpJobProtocolError, match="executionRef"):
            client.submit({"dispatchKey": "fixture"})
    assert seen == [("POST", "/v1/executions", {"dispatchKey": "fixture"})]
