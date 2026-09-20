import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multiverse_workflow.cli.main import app
from multiverse_workflow.compiler import executor_capabilities
from multiverse_workflow.runtime import registry
from multiverse_workflow.runtime.registry import ExecutorDescriptor, ExecutorRegistry

ROOT = Path(__file__).parents[2]


def test_compiler_capability_catalog_uses_local_executor_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    injected = ExecutorRegistry(
        [
            ExecutorDescriptor(
                executor_ref="test.injected.v1",
                adapter="builtin",
                capabilities=frozenset({"data.process@1"}),
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
            )
        ]
    )
    monkeypatch.setattr(registry, "local_executor_registry", lambda: injected)

    assert executor_capabilities() == injected.capability_catalog()


def test_validate_json_returns_a_serializable_execution_plan() -> None:
    result = CliRunner().invoke(
        app,
        [
            "validate",
            str(ROOT / "presets/content-delivery"),
            "--binding",
            str(ROOT / "examples/bindings/content-local.yaml"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["plans"]["delivery"]["compiledPlanDigest"].startswith("sha256:")
    assert payload["diagnostics"] == []


def test_validate_json_returns_diagnostics_and_exit_code_two() -> None:
    result = CliRunner().invoke(
        app,
        ["validate", str(ROOT / "tests/fixtures/invalid/dangling-edge"), "--json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["code"] == "INVALID_EDGE"


def test_capabilities_command_reports_support_levels() -> None:
    result = CliRunner().invoke(app, ["capabilities", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["protocolVersion"] == "multiverse/v0.1"
    by_id = {item["executorRef"]: item for item in payload["executors"]}
    assert by_id["builtin.human-input.v1"]["declared"] is True
    assert by_id["builtin.human-input.v1"]["available"] is True
    assert by_id["example.remote-content.v1"]["declared"] is True
    assert by_id["example.remote-content.v1"]["available"] is False
    assert by_id["example.remote-content.v1"]["verified"] is False
