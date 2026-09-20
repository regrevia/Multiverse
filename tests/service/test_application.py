from __future__ import annotations

from pathlib import Path

import pytest

from multiverse_workflow.service.application import RuntimeApplication
from multiverse_workflow.service.contracts import RunControlRequest, RunCreateRequest
from multiverse_workflow.service.errors import ServiceError

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "presets/content-delivery"
BINDING = ROOT / "examples/bindings/content-local.yaml"


def _application(tmp_path: Path) -> RuntimeApplication:
    return RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
    )


def _create_request() -> RunCreateRequest:
    return RunCreateRequest(
        package=str(PACKAGE),
        binding=str(BINDING),
        workflow="delivery",
        input={"goal": "write a release note"},
    )


def test_create_run_is_persisted_and_idempotent(tmp_path: Path) -> None:
    application = _application(tmp_path)

    first = application.create_run(_create_request(), idempotency_key="create-1")
    second = application.create_run(_create_request(), idempotency_key="create-1")

    assert first.resource_id.startswith("run_")
    assert first.resource_id == second.resource_id
    loaded = application.get_run("local", first.resource_id)
    assert loaded["id"] == first.resource_id
    assert loaded["version"] >= 1
    assert loaded["status"] == "waiting"


def test_control_rejects_a_stale_run_version(tmp_path: Path) -> None:
    application = _application(tmp_path)
    receipt = application.create_run(_create_request(), idempotency_key="create-1")

    with pytest.raises(ServiceError) as error:
        application.control_run(
            "local",
            receipt.resource_id,
            "pause",
            RunControlRequest(expectedVersion=1, reason="Pause for review."),
        )

    assert error.value.code == "STATE_CONFLICT"
