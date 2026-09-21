from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from multiverse_workflow.service.application import RuntimeApplication
from multiverse_workflow.service.contracts import (
    AttemptReconcileRequest,
    HumanDecisionRequest,
    RunControlRequest,
    RunCreateRequest,
)
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


def _start_worker(application: RuntimeApplication) -> None:
    application.runner.sweep(worker_id="test-worker")


def test_create_run_is_persisted_and_idempotent(tmp_path: Path) -> None:
    application = _application(tmp_path)

    first = application.create_run(_create_request(), idempotency_key="create-1")
    second = application.create_run(_create_request(), idempotency_key="create-1")

    assert first.resource_id.startswith("run_")
    assert first.resource_id == second.resource_id
    loaded = application.get_run("local", first.resource_id)
    assert loaded["id"] == first.resource_id
    assert loaded["version"] >= 1
    assert loaded["status"] == "queued"


def test_artifact_metadata_and_content_are_read_only_and_digest_checked(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path)
    created = application.create_run(_create_request(), idempotency_key="create-artifact")
    source = tmp_path / "release.md"
    source.write_text("# Release\n", encoding="utf-8")
    artifact = application.runner.ledger.register_artifact(
        run_id=created.resource_id,
        source_path=source,
        name="release.md",
        media_type="text/markdown",
    )

    metadata = application.get_artifact("local", artifact["id"])
    content = application.get_artifact_content("local", artifact["id"])

    assert metadata == {
        "id": artifact["id"],
        "namespace": "local",
        "run_id": created.resource_id,
        "invocation_id": None,
        "name": "release.md",
        "media_type": "text/markdown",
        "size_bytes": len(b"# Release\n"),
        "digest": artifact["digest"],
        "status": "ready",
        "created_at": artifact["created_at"],
    }
    assert content == b"# Release\n"

    Path(artifact["storage_ref"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(ServiceError, match="digest"):
        application.get_artifact_content("local", artifact["id"])


def test_read_models_expose_invocations_and_human_requests_with_namespace_checks(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path)
    created = application.create_run(_create_request(), idempotency_key="read-models")
    application.runner.sweep(worker_id="read-models-worker")

    invocations = application.list_invocations("local", created.resource_id)
    assert invocations
    invocation = application.get_invocation("local", invocations[0]["id"])
    assert invocation["id"] == invocations[0]["id"]
    assert invocation["run_id"] == created.resource_id
    assert invocation["input"] == {"goal": "write a release note"}
    assert invocation["input_digest"].startswith("sha256:")
    assert invocation["attempts"]
    assert "dispatch_key" not in invocation["attempts"][0]
    assert "effect_key" not in invocation["attempts"][0]

    request = application.list_human_requests("local", run_id=created.resource_id)[0]
    loaded_request = application.get_human_request("local", request["id"])
    assert loaded_request["id"] == request["id"]
    assert loaded_request["run_id"] == created.resource_id
    assert loaded_request["subject_digest"] == request["subject_digest"]

    with pytest.raises(ServiceError, match="namespace"):
        application.get_invocation("other", invocation["id"])
    with pytest.raises(ServiceError, match="namespace"):
        application.get_human_request("other", request["id"])


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
    assert restarted.get_run("local", "run_recover")["status"] == "queued"


def test_control_rejects_a_stale_run_version(tmp_path: Path) -> None:
    application = _application(tmp_path)
    receipt = application.create_run(_create_request(), idempotency_key="create-1")
    _start_worker(application)

    with pytest.raises(ServiceError) as error:
        application.control_run(
            "local",
            receipt.resource_id,
            "pause",
            RunControlRequest(expectedVersion=1, reason="Pause for review."),
            idempotency_key="pause-1",
        )

    assert error.value.code == "STATE_CONFLICT"


def test_new_control_key_cannot_reuse_a_version_already_consumed_by_another_command(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path)
    created = application.create_run(_create_request(), idempotency_key="create-1")
    current = application.get_run("local", created.resource_id)

    application.control_run(
        "local",
        created.resource_id,
        "pause",
        RunControlRequest(
            expectedVersion=current["version"],
            reason="Pause for review.",
        ),
        idempotency_key="pause-original",
    )

    with pytest.raises(ServiceError) as error:
        application.control_run(
            "local",
            created.resource_id,
            "pause",
            RunControlRequest(
                expectedVersion=current["version"],
                reason="A stale duplicate with a new key.",
            ),
            idempotency_key="pause-new-key",
        )

    assert error.value.code == "STATE_CONFLICT"


def test_control_replay_uses_the_original_transition_record(tmp_path: Path) -> None:
    application = _application(tmp_path)
    created = application.create_run(_create_request(), idempotency_key="create-1")
    current = application.get_run("local", created.resource_id)
    request = RunControlRequest(
        expectedVersion=current["version"],
        reason="Pause before the release window.",
    )
    original_finish_command = application.runner.ledger.finish_command

    def interrupt_before_receipt(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated process interruption")

    application.runner.ledger.finish_command = interrupt_before_receipt  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="interruption"):
        application.control_run(
            "local",
            created.resource_id,
            "pause",
            request,
            idempotency_key="pause-recover",
        )
    application.runner.ledger.finish_command = original_finish_command  # type: ignore[method-assign]
    application.close()

    restarted = _application(tmp_path)
    receipt = restarted.control_run(
        "local",
        created.resource_id,
        "pause",
        request,
        idempotency_key="pause-recover",
    )

    assert receipt.status == "completed"
    command = restarted.runner.ledger.get_command(receipt.request_id)
    assert command is not None
    assert command["before_version"] == current["version"]
    assert command["after_version"] == current["version"] + 1
    assert command["transition"] == "run.paused"


def test_control_replay_keeps_original_resource_version_after_later_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path)
    created = application.create_run(_create_request(), idempotency_key="create-1")
    current = application.get_run("local", created.resource_id)
    pause_request = RunControlRequest(
        expectedVersion=current["version"],
        reason="Pause before the release window.",
    )
    original_finish_command = application.runner.ledger.finish_command

    def interrupt_before_receipt(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        interrupt_before_receipt,
    )
    with pytest.raises(RuntimeError, match="interruption"):
        application.control_run(
            "local",
            created.resource_id,
            "pause",
            pause_request,
            idempotency_key="pause-recover",
        )
    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        original_finish_command,
    )

    paused = application.get_run("local", created.resource_id)
    resumed = application.control_run(
        "local",
        created.resource_id,
        "resume",
        RunControlRequest(
            expectedVersion=paused["version"],
            reason="Resume to process the pending review.",
        ),
        idempotency_key="resume-after-pause",
    )
    replayed = application.control_run(
        "local",
        created.resource_id,
        "pause",
        pause_request,
        idempotency_key="pause-recover",
    )

    assert resumed.resource_version > paused["version"]
    assert replayed.resource_version == paused["version"]
    command = application.runner.ledger.get_command_by_key(
        "pause-recover",
        namespace="local",
        subject="local-user",
        operation="run.pause",
    )
    assert command is not None
    assert command["resource_version"] == paused["version"]


def test_run_create_command_records_the_created_resource_transition(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path)

    receipt = application.create_run(_create_request(), idempotency_key="create-1")

    command = application.runner.ledger.get_command(receipt.request_id)
    assert command is not None
    assert command["before_version"] is None
    assert command["after_version"] == 1
    assert command["transition"] == "run.created"


def test_accepted_pause_command_is_resumed_after_process_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path)
    drive = application.runner._drive
    application.runner._drive = (  # type: ignore[method-assign]
        lambda run_id, scope_id, node_id: application.runner.ledger.get_run(run_id)
    )
    try:
        created = application.create_run(_create_request(), idempotency_key="create-1")
        application.runner.sweep(worker_id="setup-worker")
    finally:
        application.runner._drive = drive  # type: ignore[method-assign]
    request = RunControlRequest(
        expectedVersion=application.get_run("local", created.resource_id)["version"],
        reason="Pause before the release window.",
    )
    original_finish_command = application.runner.ledger.finish_command

    def interrupt_before_receipt(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        interrupt_before_receipt,
    )
    with pytest.raises(RuntimeError, match="interruption"):
        application.control_run(
            "local",
            created.resource_id,
            "pause",
            request,
            idempotency_key="pause-recover",
        )
    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        original_finish_command,
    )

    application.close()
    restarted = _application(tmp_path)
    receipt = restarted.control_run(
        "local",
        created.resource_id,
        "pause",
        request,
        idempotency_key="pause-recover",
    )

    assert receipt.status == "completed"
    assert restarted.get_run("local", created.resource_id)["status"] == "paused"


def test_reconciled_retry_command_is_resumed_after_process_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _write_retrying_package(tmp_path)
    application = RuntimeApplication(
        package_dir=package,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )
    drive = application.runner._drive
    application.runner._drive = (  # type: ignore[method-assign]
        lambda run_id, scope_id, node_id: application.runner.ledger.get_run(run_id)
    )
    try:
        created = application.create_run(_create_request(), idempotency_key="create-1")
        application.runner.sweep(worker_id="setup-worker")
    finally:
        application.runner._drive = drive  # type: ignore[method-assign]
    scope = application.runner.ledger.list_scopes(created.resource_id)[0]
    invocation = application.runner.ledger.create_invocation(
        created.resource_id,
        scope["id"],
        "produce",
        {"goal": "write a release note"},
    )
    application.runner.ledger.finish_invocation(invocation["id"], status="running")
    attempt = application.runner.ledger.create_attempt(
        invocation["id"],
        input_value={"goal": "write a release note"},
        dispatch_key=f"{invocation['id']}:1",
        effect_key=invocation["id"],
    )
    application.runner.ledger.finish_attempt(attempt["id"], status="running")
    unknown = application.runner.ledger.finish_attempt(attempt["id"], status="unknown")
    application.runner.ledger.update_run(
        created.resource_id,
        status="running",
        current_scope_id=scope["id"],
        current_node_id="produce",
        current_invocation_id=invocation["id"],
    )
    request = AttemptReconcileRequest(
        expectedVersion=unknown["version"],
        conclusion="confirmed_not_started",
        evidenceRefs=["evidence://provider/not-started"],
        reason="The provider confirmed that the old submission was never accepted.",
    )
    original_finish_command = application.runner.ledger.finish_command

    def interrupt_before_receipt(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        interrupt_before_receipt,
    )
    with pytest.raises(RuntimeError, match="interruption"):
        application.reconcile_attempt(
            "local",
            unknown["id"],
            request,
            idempotency_key="reconcile-recover",
        )
    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        original_finish_command,
    )
    application.close()

    restarted = RuntimeApplication(
        package_dir=package,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )
    receipt = restarted.reconcile_attempt(
        "local",
        unknown["id"],
        request,
        idempotency_key="reconcile-recover",
    )

    assert receipt.status == "completed"
    assert restarted.runner.ledger.get_command_by_key(
        "reconcile-recover",
        namespace="local",
        subject="example-reviewer",
        operation="attempt.reconcile",
    )["status"] == "completed"
    assert restarted.runner.ledger.get_invocation(invocation["id"])["status"] == (
        "reconciling"
    )
    wait = restarted.runner.ledger.get_wait_by_key(
        "local", f"attempt-reconcile:{unknown['id']}"
    )
    assert wait is not None
    assert wait["status"] == "pending"
    restarted.runner.sweep(worker_id="restarted-worker")
    assert restarted.runner.ledger.get_invocation(invocation["id"])["status"] == (
        "succeeded"
    )


def test_attempt_version_conflict_exposes_expected_and_actual_versions(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path)
    created = application.create_run(_create_request(), idempotency_key="create-1")
    _start_worker(application)
    invocation = application.runner.ledger.list_invocations(created.resource_id)[-1]
    attempt = application.runner.ledger.latest_attempt(invocation["id"])
    assert attempt is not None
    unknown = application.runner.ledger.finish_attempt(attempt["id"], status="unknown")
    request = AttemptReconcileRequest(
        expectedVersion=unknown["version"] - 1,
        conclusion="confirmed_failed",
        evidenceRefs=["evidence://provider/failed"],
        reason="The provider confirmed a failure.",
    )

    with pytest.raises(ServiceError) as error:
        application.reconcile_attempt(
            "local",
            unknown["id"],
            request,
            idempotency_key="reconcile-version",
        )

    assert error.value.code == "STATE_CONFLICT"
    assert error.value.details == {
        "resourceId": unknown["id"],
        "expectedVersion": unknown["version"] - 1,
        "actualVersion": unknown["version"],
    }


def test_command_query_is_hidden_from_another_authenticated_subject(
    tmp_path: Path,
) -> None:
    first_application = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="first-reviewer",
    )
    created = first_application.create_run(_create_request(), idempotency_key="create-1")
    first_application.close()

    second_application = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="second-reviewer",
    )

    with pytest.raises(ServiceError) as error:
        second_application.get_command("local", created.request_id)

    assert error.value.code == "NOT_FOUND"


def _write_retrying_package(root: Path) -> Path:
    package = root / "retrying-content"
    shutil.copytree(ROOT / "presets/content-delivery", package)
    workflow_path = package / "workflows/delivery.yaml"
    workflow = workflow_path.read_text(encoding="utf-8").replace(
        """      retry:
        maxAttempts: 1
      next: critique
""",
        """      retry:
        maxAttempts: 2
      next: critique
""",
        1,
    )
    workflow_path.write_text(workflow, encoding="utf-8")
    return package


def test_reconcile_attempt_is_idempotent_and_records_authenticated_actor(
    tmp_path: Path,
) -> None:
    application = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )
    created = application.create_run(_create_request(), idempotency_key="create-1")
    _start_worker(application)
    invocation = application.runner.ledger.list_invocations(created.resource_id)[-1]
    attempt = application.runner.ledger.latest_attempt(invocation["id"])
    assert attempt is not None
    unknown = application.runner.ledger.finish_attempt(attempt["id"], status="unknown")
    request = AttemptReconcileRequest(
        expectedVersion=unknown["version"],
        conclusion="confirmed_failed",
        evidenceRefs=["evidence://provider/failed"],
        reason="The provider confirmed the execution failed.",
    )

    first = application.reconcile_attempt(
        "local",
        unknown["id"],
        request,
        idempotency_key="reconcile-1",
    )
    second = application.reconcile_attempt(
        "local",
        unknown["id"],
        request,
        idempotency_key="reconcile-1",
    )

    assert first.request_id == second.request_id
    reconciled = application.runner.ledger.get_attempt(unknown["id"])
    assert reconciled is not None
    assert reconciled["status"] == "failed"
    assert '"actor": "example-reviewer"' in reconciled["reconciliation_json"]


def test_reconcile_idempotency_key_is_scoped_by_authenticated_subject(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.db"
    first_application = _application(tmp_path)
    created = first_application.create_run(_create_request(), idempotency_key="create-1")
    _start_worker(first_application)
    invocation = first_application.runner.ledger.list_invocations(created.resource_id)[-1]
    attempt = first_application.runner.ledger.latest_attempt(invocation["id"])
    assert attempt is not None
    unknown = first_application.runner.ledger.finish_attempt(attempt["id"], status="unknown")
    request = AttemptReconcileRequest(
        expectedVersion=unknown["version"],
        conclusion="confirmed_failed",
        evidenceRefs=["evidence://provider/failed"],
        reason="The provider confirmed the execution failed.",
    )
    first_application.reconcile_attempt(
        "local",
        unknown["id"],
        request,
        idempotency_key="reconcile-subject",
    )
    first_application.close()

    second_application = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=database,
        deployment_id="deployment_local",
        subject="another-reviewer",
    )
    with pytest.raises(ServiceError) as error:
        second_application.reconcile_attempt(
            "local",
            unknown["id"],
            request,
            idempotency_key="reconcile-subject",
        )

    assert error.value.code == "STATE_CONFLICT"


def test_accepted_reconcile_command_is_resumed_after_process_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )
    created = application.create_run(_create_request(), idempotency_key="create-1")
    _start_worker(application)
    invocation = application.runner.ledger.list_invocations(created.resource_id)[-1]
    attempt = application.runner.ledger.latest_attempt(invocation["id"])
    assert attempt is not None
    unknown = application.runner.ledger.finish_attempt(attempt["id"], status="unknown")
    request = AttemptReconcileRequest(
        expectedVersion=unknown["version"],
        conclusion="confirmed_failed",
        evidenceRefs=["evidence://provider/failed"],
        reason="The provider confirmed the execution failed.",
    )
    original_finish_command = application.runner.ledger.finish_command

    def interrupt_before_receipt(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        interrupt_before_receipt,
    )
    with pytest.raises(RuntimeError, match="interruption"):
        application.reconcile_attempt(
            "local",
            unknown["id"],
            request,
            idempotency_key="reconcile-recover",
        )
    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        original_finish_command,
    )
    command = application.runner.ledger.get_command_by_key("reconcile-recover")
    assert command is not None
    assert command["status"] == "accepted"
    application.close()

    restarted = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )
    receipt = restarted.reconcile_attempt(
        "local",
        unknown["id"],
        request,
        idempotency_key="reconcile-recover",
    )

    assert receipt.request_id == command["id"]
    assert restarted.runner.ledger.get_command(command["id"])["status"] == "completed"


def test_accepted_human_decision_command_is_resumed_after_process_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )
    created = application.create_run(_create_request(), idempotency_key="create-1")
    _start_worker(application)
    human_request = application.list_human_requests(
        "local",
        run_id=created.resource_id,
        status="pending",
    )[0]
    request = HumanDecisionRequest(
        expectedVersion=human_request["version"],
        subjectDigest=human_request["subject_digest"],
        choice="approve",
        comment="Approved.",
    )
    original_finish_command = application.runner.ledger.finish_command

    def interrupt_before_receipt(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        interrupt_before_receipt,
    )
    with pytest.raises(RuntimeError, match="interruption"):
        application.decide_human_request(
            "local",
            human_request["id"],
            request,
            idempotency_key="decision-recover",
        )
    decision = application.runner.ledger.get_human_decision(human_request["id"])
    assert decision is not None
    assert application.runner.ledger.get_human_progress_intent(
        human_request["id"]
    )["status"] == "pending"
    events_before_restart = application.runner.ledger.list_events(created.resource_id)
    assert sum(
        event["type"] == "human.decided" for event in events_before_restart
    ) == 1
    monkeypatch.setattr(
        application.runner.ledger,
        "finish_command",
        original_finish_command,
    )
    application.close()

    restarted = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )
    receipt = restarted.decide_human_request(
        "local",
        human_request["id"],
        request,
        idempotency_key="decision-recover",
    )
    restarted.runner.sweep(worker_id="test-worker")

    assert receipt.status == "completed"
    command = restarted.runner.ledger.get_command(receipt.request_id)
    assert command is not None
    assert command["status"] == "completed"
    assert command["before_version"] == 1
    assert command["after_version"] == 2
    assert command["transition"] == "human.decided"
    assert restarted.runner.ledger.get_invocation(
        human_request["invocation_id"]
    )["status"] == "succeeded"
    assert restarted.runner.ledger.get_human_decision(human_request["id"])["id"] == (
        decision["id"]
    )
    assert restarted.runner.ledger.get_human_progress_intent(
        human_request["id"]
    )["status"] == "completed"
    events_after_restart = restarted.runner.ledger.list_events(created.resource_id)
    assert sum(event["type"] == "human.decided" for event in events_after_restart) == 1
    assert len(events_after_restart) > len(events_before_restart)


def test_human_decision_recovery_drives_persisted_next_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )
    created = application.create_run(_create_request(), idempotency_key="create-1")
    _start_worker(application)
    human_request = application.list_human_requests(
        "local",
        run_id=created.resource_id,
        status="pending",
    )[0]
    request = HumanDecisionRequest(
        expectedVersion=human_request["version"],
        subjectDigest=human_request["subject_digest"],
        choice="approve",
        comment="Approved.",
    )
    def interrupt_before_drive(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated worker interruption")

    application.decide_human_request(
        "local",
        human_request["id"],
        request,
        idempotency_key="decision-recover",
    )
    monkeypatch.setattr(application.runner, "_drive", interrupt_before_drive)
    with pytest.raises(RuntimeError, match="worker interruption"):
        application.runner.sweep(worker_id="test-worker")
    run_after_interruption = application.get_run("local", created.resource_id)
    assert run_after_interruption["status"] == "running"
    assert run_after_interruption["current_node_id"] == "review-route"
    assert application.runner.ledger.get_human_progress_intent(
        human_request["id"]
    )["status"] == "pending"
    application.close()

    restarted = RuntimeApplication(
        package_dir=PACKAGE,
        binding_path=BINDING,
        database_path=tmp_path / "runtime.db",
        deployment_id="deployment_local",
        subject="example-reviewer",
    )
    receipt = restarted.decide_human_request(
        "local",
        human_request["id"],
        request,
        idempotency_key="decision-recover",
    )
    restarted.runner.sweep(worker_id="test-worker")

    assert receipt.status == "completed"
    assert restarted.get_run("local", created.resource_id)["status"] == "succeeded"
