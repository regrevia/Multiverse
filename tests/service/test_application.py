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
        deployment_id="deployment_local",
    )


def _create_request() -> RunCreateRequest:
    return RunCreateRequest(
        deploymentId="deployment_local",
        workflowId="delivery",
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


def test_command_receipt_survives_application_restart(tmp_path: Path) -> None:
    first_application = _application(tmp_path)
    first = first_application.create_run(_create_request(), idempotency_key="create-1")
    first_application.close()

    second_application = _application(tmp_path)
    second = second_application.create_run(_create_request(), idempotency_key="create-1")

    assert second.request_id == first.request_id
    assert second.resource_id == first.resource_id
    command = second_application.get_command("local", first.request_id)
    assert command["status"] == "completed"
    assert command["resource_id"] == first.resource_id


def test_reusing_command_key_with_different_request_is_a_conflict(tmp_path: Path) -> None:
    application = _application(tmp_path)
    application.create_run(_create_request(), idempotency_key="create-1")

    with pytest.raises(ServiceError) as error:
        application.create_run(
            RunCreateRequest(
                deploymentId="deployment_local",
                workflowId="delivery",
                input={"goal": "different"},
            ),
            idempotency_key="create-1",
        )

    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_accepted_create_command_is_resumed_with_original_run_id(tmp_path: Path) -> None:
    application = _application(tmp_path)
    command_id = "cmd_recover"
    application.runner.ledger.create_command(
        command_id=command_id,
        idempotency_key="create-recover",
        fingerprint=application._fingerprint(_create_request()),
        operation="run.create",
        namespace="local",
        resource_id="run_recover",
    )
    application.close()

    restarted = _application(tmp_path)
    receipt = restarted.create_run(_create_request(), idempotency_key="create-recover")

    assert receipt.request_id == command_id
    assert receipt.resource_id == "run_recover"
    assert restarted.get_run("local", "run_recover")["status"] == "waiting"


def test_control_rejects_a_stale_run_version(tmp_path: Path) -> None:
    application = _application(tmp_path)
    receipt = application.create_run(_create_request(), idempotency_key="create-1")

    with pytest.raises(ServiceError) as error:
        application.control_run(
            "local",
            receipt.resource_id,
            "pause",
            RunControlRequest(expectedVersion=1, reason="Pause for review."),
            idempotency_key="pause-1",
        )

    assert error.value.code == "STATE_CONFLICT"
