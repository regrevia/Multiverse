from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from ruamel.yaml import YAML

from multiverse_workflow.api.app import create_app
from multiverse_workflow.api.dependencies import ServiceSettings
from multiverse_workflow.runtime.executors import execute_codex
from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry
from multiverse_workflow.runtime.runner import Runner
from multiverse_workflow.runtime.worker import LocalWorker

pytestmark = pytest.mark.integration


def _live_registry() -> ExecutorRegistry:
    return ExecutorRegistry(
        [
            replace(descriptor, verified=True)
            if descriptor.executor_ref == "builtin.codex-deliverable.v1"
            else descriptor
            for descriptor in local_executor_registry().descriptors()
        ]
    )


def _write_live_binding(tmp_path: Path) -> Path:
    return _write_binding_with_codex_config(tmp_path, {})


def _write_binding_with_codex_config(
    tmp_path: Path, codex_overrides: dict[str, object]
) -> Path:
    binding = YAML(typ="safe").load(
        (Path(__file__).parents[2] / "examples/bindings/content-local.yaml").read_text()
    )
    producer = binding["spec"]["slots"]["producer"]
    producer["adapter"] = "codex"
    producer["executorRef"] = "builtin.codex-deliverable.v1"
    producer["config"] = {
        "cwd": str(tmp_path),
        "workspaceRoot": str(tmp_path),
        "homeDir": str(Path(os.environ.get("HOME", str(tmp_path))).resolve()),
        "interactionAuthorizedSubjects": ["example-reviewer"],
        "model": os.environ.get("MULTIVERSE_CODEX_MODEL", "gpt-5.5"),
        "systemPrompt": (
            "Return only concise JSON with a non-empty text field and an empty "
            "artifact_refs array. Do not use tools or invent Artifact IDs."
        ),
        "artifactName": "codex-runtime-deliverable.md",
        "artifactMediaType": "text/markdown",
        "timeoutSeconds": 180,
        **codex_overrides,
    }
    binding_path = tmp_path / "binding.yaml"
    with binding_path.open("w", encoding="utf-8") as handle:
        YAML().dump(binding, handle)
    return binding_path


def test_real_coding_delivery_probe_reaches_runtime_shaped_output(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized local Codex probe")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the coding delivery probe")

    result = execute_codex(
        {
            "goal": (
                "Prepare a concise release note for Multiverse. "
                "Return a useful human-reviewable deliverable."
            )
        },
        {
            "cwd": str(tmp_path),
            "workspaceRoot": str(tmp_path),
            "homeDir": str(Path(os.environ.get("HOME", str(tmp_path))).resolve()),
            "model": os.environ.get("MULTIVERSE_CODEX_MODEL", "gpt-5.5"),
            "systemPrompt": (
                "Act as the producer node for a human-reviewed delivery workflow. "
                "Return only JSON with non-empty text and an empty artifact_refs array."
            ),
            "artifactName": "coding-delivery-probe.md",
            "artifactMediaType": "text/markdown",
            "timeoutSeconds": 180,
        },
    )

    assert result.generated_artifact is not None
    assert result.output["artifact_refs"] == []
    assert result.observations


def test_real_coding_delivery_completes_runtime_human_loop(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized local Codex loop")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the coding delivery loop")

    binding_path = _write_live_binding(tmp_path)
    registry = _live_registry()
    runner = Runner(
        Path(__file__).parents[2] / "presets/content-delivery",
        binding_path=binding_path,
        database_path=tmp_path / "runtime.db",
        executor_registry=registry,
    )

    try:
        waiting = runner.start(
            {"goal": "Write a concise release note for the Multiverse runtime."}
        )
        assert waiting["status"] == "waiting"
        request = runner.pending_human_requests(waiting["id"])[0]
        assert request["authorized_subjects_json"] == '["example-reviewer"]'
        artifacts = runner.ledger.list_artifacts(run_id=waiting["id"])
        assert artifacts and artifacts[0]["status"] == "ready"

        finished = runner.decide(
            request["id"],
            choice="approve",
            comment="Approved by the authorized reviewer.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
            idempotency_key="real-coding-delivery-e2e",
        )

        assert finished["status"] == "succeeded"
        output = json.loads(finished["output_json"])
        assert output["review"]["decision"] == "approve"
        assert output["deliverable"]["artifact_refs"]
        decision = runner.ledger.get_human_decision(request["id"])
        assert decision is not None
        artifact = runner.ledger.get_artifact(output["deliverable"]["artifact_refs"][0])
        assert artifact is not None
        attempts = runner.ledger.list_attempts(waiting["id"])
        print(
            f"coding_delivery_live_run_id={waiting['id']} request_id={request['id']} "
            f"decision_id={decision['id']} actor={decision['actor']} "
            f"subject_digest={decision['subject_digest']} "
            f"expected_version={request['version']} decision_version={decision['request_version']} "
            f"attempt_ids={[item['id'] for item in attempts]} "
            f"artifact_id={artifact['id']} artifact_digest={artifact['digest']} "
            f"terminal_status={finished['status']}"
        )
    finally:
        runner.close()


def test_real_coding_delivery_rejects_with_authorized_human(tmp_path: Path) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized reject loop")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the coding delivery reject loop")

    binding_path = _write_live_binding(tmp_path)
    registry = _live_registry()
    runner = Runner(
        Path(__file__).parents[2] / "presets/content-delivery",
        binding_path=binding_path,
        database_path=tmp_path / "runtime.db",
        executor_registry=registry,
    )
    try:
        waiting = runner.start({"goal": "Write a concise release note for rejection testing."})
        assert waiting["status"] == "waiting"
        request = runner.pending_human_requests(waiting["id"])[0]
        attempts_before = len(runner.ledger.list_attempts(waiting["id"]))
        artifacts_before = len(runner.ledger.list_artifacts(run_id=waiting["id"]))
        finished = runner.decide(
            request["id"],
            choice="reject",
            comment="Rejected by the authorized reviewer for live rejection evidence.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
            idempotency_key="real-coding-delivery-reject",
        )
        assert finished["status"] == "failed"
        assert json.loads(finished["error_json"])["code"] == "DELIVERABLE_REJECTED"
        decision = runner.ledger.get_human_decision(request["id"])
        assert decision is not None
        assert decision["choice"] == "reject"
        assert decision["actor"] == "example-reviewer"
        assert decision["request_version"] == request["version"] + 1
        print(
            f"reject_live_run_id={waiting['id']} request_id={request['id']} "
            f"decision_id={decision['id']} actor={decision['actor']} "
            f"subject_digest={decision['subject_digest']} "
            f"expected_version={request['version']} decision_version={decision['request_version']} "
            f"artifact_count={artifacts_before}"
        )
        assert len(runner.ledger.list_attempts(waiting["id"])) == attempts_before
        assert len(runner.ledger.list_artifacts(run_id=waiting["id"])) == artifacts_before
        replay = runner.decide(
            request["id"],
            choice="reject",
            comment="Rejected by the authorized reviewer for live rejection evidence.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
            idempotency_key="real-coding-delivery-reject",
        )
        assert replay["status"] == "failed"
        print(
            f"reject_live_run_id={waiting['id']} request_id={request['id']} "
            f"decision_id={decision['id']} actor={decision['actor']} "
            f"subject_digest={decision['subject_digest']} "
            f"expected_version={request['version']} "
            f"decision_version={decision['request_version']} "
            f"terminal_error={json.loads(finished['error_json'])['code']}"
        )
    finally:
        runner.close()


def test_real_coding_delivery_survives_runtime_restart_before_approval(
    tmp_path: Path,
) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized restart loop")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the restart loop")

    package = Path(__file__).parents[2] / "presets/content-delivery"
    binding_path = _write_live_binding(tmp_path)
    registry = _live_registry()
    database = tmp_path / "runtime.db"
    runner = Runner(
        package,
        binding_path=binding_path,
        database_path=database,
        executor_registry=registry,
    )
    waiting = runner.start({"goal": "Write a concise release note for Multiverse."})
    assert waiting["status"] == "waiting"
    run_id = waiting["id"]
    original_requests = runner.pending_human_requests(run_id)
    assert len(original_requests) == 1
    original_request_id = original_requests[0]["id"]
    before_attempts = len(runner.ledger.list_attempts(run_id))
    before_artifacts = len(runner.ledger.list_artifacts(run_id=run_id))
    runner.close()

    restarted = Runner(
        package,
        binding_path=binding_path,
        database_path=database,
        executor_registry=registry,
    )
    try:
        recovered_requests = restarted.pending_human_requests(run_id)
        assert len(recovered_requests) == 1
        request = recovered_requests[0]
        assert request["id"] == original_request_id
        print(f"restart_e2e_run_id={run_id}")
        finished = restarted.decide(
            request["id"],
            choice="approve",
            comment="Approved after runtime restart.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
            idempotency_key="real-coding-delivery-restart-approve",
        )
        assert finished["status"] == "succeeded"
        assert len(restarted.ledger.list_attempts(run_id)) == before_attempts
        assert len(restarted.ledger.list_artifacts(run_id=run_id)) == before_artifacts
        replay = restarted.decide(
            request["id"],
            choice="approve",
            comment="Approved after runtime restart.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
            idempotency_key="real-coding-delivery-restart-approve",
        )
        assert replay["status"] == "succeeded"
        decision = restarted.ledger.get_human_decision(request["id"])
        assert decision is not None
        print(
            f"runtime_restart_run_id={run_id} request_id={request['id']} "
            f"decision_id={decision['id']} decision_actor={decision['actor']} "
            f"attempt_count={len(restarted.ledger.list_attempts(run_id))} "
            f"artifact_count={len(restarted.ledger.list_artifacts(run_id=run_id))}"
        )
        assert len(restarted.ledger.list_attempts(run_id)) == before_attempts
    finally:
        restarted.close()


def test_real_coding_delivery_survives_worker_restart_before_approval(
    tmp_path: Path,
) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run the authorized worker restart loop")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the worker restart loop")

    package = Path(__file__).parents[2] / "presets/content-delivery"
    binding_path = _write_live_binding(tmp_path)
    registry = _live_registry()
    database = tmp_path / "runtime.db"
    runner = Runner(
        package,
        binding_path=binding_path,
        database_path=database,
        executor_registry=registry,
    )
    waiting = runner.start({"goal": "Write a concise release note for Multiverse."})
    run_id = waiting["id"]
    print(f"worker_restart_e2e_run_id={run_id}")
    original_request = runner.pending_human_requests(run_id)[0]
    before_attempts = len(runner.ledger.list_attempts(run_id))
    before_artifacts = len(runner.ledger.list_artifacts(run_id=run_id))
    runner.close()

    worker = LocalWorker.from_paths(
        package_dir=package,
        binding_path=binding_path,
        database_path=database,
        namespace="local",
        worker_id="live-worker-restart",
        poll_interval=0,
        executor_registry=registry,
    )
    try:
        worker.run_once()
    finally:
        worker.close()

    restarted = Runner(
        package,
        binding_path=binding_path,
        database_path=database,
        executor_registry=registry,
    )
    try:
        recovered = restarted.pending_human_requests(run_id)
        assert len(recovered) == 1
        assert recovered[0]["id"] == original_request["id"]
        finished = restarted.decide(
            recovered[0]["id"],
            choice="approve",
            comment="Approved after worker restart.",
            actor="example-reviewer",
            subject_digest=recovered[0]["subject_digest"],
            expected_version=recovered[0]["version"],
            idempotency_key="real-coding-delivery-worker-restart",
        )
        assert finished["status"] == "succeeded"
        assert len(restarted.ledger.list_attempts(run_id)) == before_attempts
        assert len(restarted.ledger.list_artifacts(run_id=run_id)) == before_artifacts
    finally:
        restarted.close()


def test_real_coding_delivery_survives_worker_stop_and_restart_exactly_once(
    tmp_path: Path,
) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_LIVE") != "1":
        pytest.skip("set MULTIVERSE_RUN_CODEX_LIVE=1 to run worker stop/restart evidence")
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for worker stop/restart evidence")

    package = Path(__file__).parents[2] / "presets/content-delivery"
    binding_path = _write_live_binding(tmp_path)
    registry = _live_registry()
    database = tmp_path / "runtime.db"
    runner = Runner(
        package,
        binding_path=binding_path,
        database_path=database,
        executor_registry=registry,
    )
    waiting = runner.start({"goal": "Write a concise release note for worker stop testing."})
    assert waiting["status"] == "waiting"
    run_id = waiting["id"]
    request = runner.pending_human_requests(run_id)[0]
    before_attempts = len(runner.ledger.list_attempts(run_id))
    before_artifacts = len(runner.ledger.list_artifacts(run_id=run_id))
    runner.close()

    stop_event = threading.Event()
    worker_ready = threading.Event()
    worker_stopped = threading.Event()
    worker_error: list[BaseException] = []

    def run_worker() -> None:
        worker = LocalWorker.from_paths(
            package_dir=package,
            binding_path=binding_path,
            database_path=database,
            namespace="local",
            worker_id="live-stop-restart-worker-1",
            poll_interval=0.05,
            executor_registry=registry,
        )
        try:
            worker_ready.set()
            worker.run_forever(stop_event=stop_event)
        except BaseException as exc:
            worker_error.append(exc)
        finally:
            worker.close()
            worker_stopped.set()

    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()
    assert worker_ready.wait(timeout=5)
    time.sleep(0.2)
    stop_event.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert worker_stopped.is_set()
    assert not worker_error

    controller = Runner(
        package,
        binding_path=binding_path,
        database_path=database,
        executor_registry=registry,
    )
    try:
        recovered = controller.pending_human_requests(run_id)
        assert len(recovered) == 1
        assert recovered[0]["id"] == request["id"]
        decided = controller.decide(
            recovered[0]["id"],
            choice="approve",
            comment="Approve after worker restart; let the restarted worker resume.",
            actor="example-reviewer",
            subject_digest=recovered[0]["subject_digest"],
            expected_version=recovered[0]["version"],
            idempotency_key="real-coding-delivery-worker-stop-restart",
            resume=False,
        )
        assert decided["status"] == "waiting"

        resumed_stop = threading.Event()
        resumed_ready = threading.Event()
        resumed_stopped = threading.Event()
        resumed_error: list[BaseException] = []

        def run_restarted_worker() -> None:
            resumed_worker = LocalWorker.from_paths(
                package_dir=package,
                binding_path=binding_path,
                database_path=database,
                namespace="local",
                worker_id="live-stop-restart-worker-2",
                poll_interval=0.05,
                executor_registry=registry,
            )
            try:
                resumed_ready.set()
                resumed_worker.run_forever(stop_event=resumed_stop)
            except BaseException as exc:
                resumed_error.append(exc)
            finally:
                resumed_worker.close()
                resumed_stopped.set()

        resumed_thread = threading.Thread(target=run_restarted_worker, daemon=True)
        resumed_thread.start()
        assert resumed_ready.wait(timeout=5)
        terminal_deadline = time.monotonic() + 30
        final = controller.ledger.get_run(run_id)
        while time.monotonic() < terminal_deadline and final["status"] not in {
            "succeeded",
            "failed",
            "blocked",
            "cancelled",
        }:
            time.sleep(0.05)
            final = controller.ledger.get_run(run_id)
        assert final["status"] == "succeeded"
        resumed_stop.set()
        resumed_thread.join(timeout=5)
        assert not resumed_thread.is_alive()
        assert resumed_stopped.is_set()
        assert not resumed_error
        assert len(controller.ledger.list_attempts(run_id)) == before_attempts
        assert len(controller.ledger.list_artifacts(run_id=run_id)) == before_artifacts
        replay = controller.decide(
            recovered[0]["id"],
            choice="approve",
            comment="Approve after worker restart; let the restarted worker resume.",
            actor="example-reviewer",
            subject_digest=recovered[0]["subject_digest"],
            expected_version=recovered[0]["version"],
            idempotency_key="real-coding-delivery-worker-stop-restart",
            resume=False,
        )
        assert replay["status"] == "succeeded"
        decision = controller.ledger.get_human_decision(request["id"])
        assert decision is not None
        assert decision["actor"] == "example-reviewer"
        assert decision["subject_digest"] == request["subject_digest"]
        print(
            f"worker_stop_restart_run_id={run_id} request_id={request['id']} "
            f"decision_id={decision['id']} actor={decision['actor']} "
            f"subject_digest={decision['subject_digest']} "
            f"expected_version={request['version']} "
            f"attempt_count={len(controller.ledger.list_attempts(run_id))} "
            f"artifact_count={len(controller.ledger.list_artifacts(run_id=run_id))}"
        )
    finally:
        controller.close()


@pytest.mark.anyio
async def test_real_codex_native_approval_is_persisted_replied_and_resumed(
    tmp_path: Path,
) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_INTERACTION_LIVE") != "1":
        pytest.skip(
            "set MULTIVERSE_RUN_CODEX_INTERACTION_LIVE=1 to run the native approval flow"
        )
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the native approval flow")

    package = Path(__file__).parents[2] / "presets/content-delivery"
    binding_path = _write_binding_with_codex_config(
        tmp_path,
        {
            "approvalPolicy": "untrusted",
            "sandboxMode": "workspace-write",
            "timeoutSeconds": 120,
        },
    )
    registry = _live_registry()
    database = tmp_path / "runtime.db"
    settings = ServiceSettings(
        database_path=database,
        package_dir=package,
        binding_path=binding_path,
        bearer_token="native-interaction-test-token",
        subject="example-reviewer",
        executor_registry=registry,
    )
    app = create_app(settings)
    worker_stop = threading.Event()
    worker_failure: list[BaseException] = []

    def run_worker() -> None:
        worker = LocalWorker.from_paths(
            package_dir=package,
            binding_path=binding_path,
            database_path=database,
            namespace="local",
            worker_id="live-native-interaction-worker",
            poll_interval=0.05,
            executor_registry=registry,
        )
        try:
            worker.run_forever(stop_event=worker_stop)
        except BaseException as exc:
            worker_failure.append(exc)
        finally:
            worker.close()

    worker_thread = threading.Thread(target=run_worker, daemon=True)
    interaction_id: str | None = None
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/namespaces/local/runs",
                headers={
                    "Authorization": "Bearer native-interaction-test-token",
                    "Idempotency-Key": "native-interaction-live-run",
                },
                json={
                    "deploymentId": "deployment_local",
                    "workflowId": "delivery",
                    "input": {
                        "goal": (
                            "This task requires an actual shell command execution. You must "
                            "invoke the shell to create approval-probe.txt in the current "
                            "workspace containing the text authorized write completed. Do "
                            "not claim the file was written unless the shell command succeeds. "
                            "After that command succeeds, return the required JSON deliverable."
                        )
                    },
                },
            )
            assert created.status_code == 202, created.text
            run_id = created.json()["resourceId"]
            worker_thread.start()
            headers = {"Authorization": "Bearer native-interaction-test-token"}
            wait_deadline = time.monotonic() + 90
            pending: dict[str, object] | None = None
            while time.monotonic() < wait_deadline:
                response = await client.get(
                    f"/api/v1/namespaces/local/runs/{run_id}/codex-interactions"
                    "?status=pending",
                    headers=headers,
                )
                assert response.status_code == 200, response.text
                items = response.json()["interactions"]
                if items:
                    pending = items[0]
                    break
                run_state = (await client.get(
                    f"/api/v1/namespaces/local/runs/{run_id}",
                    headers=headers,
                )).json()
                if run_state["status"] in {"failed", "blocked", "cancelled"}:
                    pytest.fail(
                        f"Run ended before native approval: {run_state['status']}; "
                        f"worker={worker_failure!r}"
                    )
                await asyncio.sleep(0.1)

            assert pending is not None, (
                f"Codex produced no native approval request; worker={worker_failure!r}"
            )
            assert pending["kind"] in {
                "item/commandExecution/requestApproval",
                "item/fileChange/requestApproval",
            }
            interaction_id = str(pending["id"])
            responded = await client.post(
                f"/api/v1/namespaces/local/codex-interactions/{interaction_id}/responses",
                headers={
                    **headers,
                    "Idempotency-Key": "native-interaction-live-accept",
                },
                json={
                    "expectedVersion": pending["version"],
                    "response": {"decision": "accept"},
                },
            )
            assert responded.status_code == 202, responded.text
            assert responded.json()["status"] == "replied"

            delivery_deadline = time.monotonic() + 20
            while time.monotonic() < delivery_deadline:
                observed = (await client.get(
                    f"/api/v1/namespaces/local/codex-interactions/{interaction_id}",
                    headers=headers,
                )).json()
                if observed["deliveryStatus"] == "sent":
                    break
                await asyncio.sleep(0.05)
            assert observed["deliveryStatus"] == "sent"

            write_deadline = time.monotonic() + 45
            probe_file = tmp_path / "approval-probe.txt"
            while time.monotonic() < write_deadline and not probe_file.exists():
                await asyncio.sleep(0.05)
            assert probe_file.exists(), (
                "Codex approval response was sent but command had no file effect"
            )
            written = probe_file.read_text().strip()
            assert written.rstrip(".!") == "authorized write completed"
            request_deadline = time.monotonic() + 120
            human_request: dict[str, object] | None = None
            while time.monotonic() < request_deadline:
                response = await client.get(
                    f"/api/v1/namespaces/local/human-requests?runId={run_id}&status=pending",
                    headers=headers,
                )
                assert response.status_code == 200, response.text
                requests = response.json()["requests"]
                if requests:
                    human_request = requests[0]
                    break
                await asyncio.sleep(0.1)
            assert human_request is not None

            business_decision = await client.post(
                f"/api/v1/namespaces/local/human-requests/{human_request['id']}/decisions",
                headers={
                    **headers,
                    "Idempotency-Key": "native-interaction-live-business-approve",
                },
                json={
                    "expectedVersion": human_request["version"],
                    "subjectDigest": human_request["subjectDigest"],
                    "choice": "approve",
                    "comment": "Native tool approval and business review are distinct.",
                },
            )
            assert business_decision.status_code == 202, business_decision.text

            terminal_deadline = time.monotonic() + 30
            final_run: dict[str, object] = {}
            while time.monotonic() < terminal_deadline:
                final_run = (await client.get(
                    f"/api/v1/namespaces/local/runs/{run_id}",
                    headers=headers,
                )).json()
                if final_run["status"] in {"succeeded", "failed", "blocked", "cancelled"}:
                    break
                await asyncio.sleep(0.1)
            assert final_run["status"] == "succeeded"
            print(
                f"native_interaction_live_run_id={run_id} "
                f"interaction_id={interaction_id}"
            )
    finally:
        worker_stop.set()
        if worker_thread.is_alive():
            worker_thread.join(timeout=5)
        app.state.runtime.close()


def test_real_codex_native_approval_round_trip_continues_same_turn(
    tmp_path: Path,
) -> None:
    if os.environ.get("MULTIVERSE_RUN_CODEX_INTERACTION_LIVE") != "1":
        pytest.skip(
            "set MULTIVERSE_RUN_CODEX_INTERACTION_LIVE=1 to run the native approval flow"
        )
    if shutil.which("codex") is None:
        pytest.fail("codex executable is required for the native interaction test")

    package = Path(__file__).parents[2] / "presets/content-delivery"
    binding_path = _write_binding_with_codex_config(
        tmp_path,
        {
            "approvalPolicy": "on-request",
            "sandboxMode": "read-only",
            "timeoutSeconds": 240,
        },
    )
    registry = _live_registry()
    database = tmp_path / "runtime.db"
    main_runner = Runner(
        package,
        binding_path=binding_path,
        database_path=database,
        executor_registry=registry,
    )
    result_holder: list[dict[str, object]] = []
    failure_holder: list[BaseException] = []

    def run_workflow() -> None:
        worker_runner = Runner(
            package,
            binding_path=binding_path,
            database_path=database,
            executor_registry=registry,
        )
        try:
            result_holder.append(
                worker_runner.start(
                    {
                        "goal": (
                            "Use the shell to create approval-probe.txt in the current "
                            "workspace containing exactly 'authorized write completed'. "
                            "The workspace is read-only until a reviewer approves the "
                            "native command request. After the write succeeds, return a "
                            "concise release note as structured JSON."
                        )
                    }
                )
            )
        except BaseException as exc:
            failure_holder.append(exc)
        finally:
            worker_runner.close()

    workflow_thread = threading.Thread(target=run_workflow, daemon=True)
    workflow_thread.start()
    deadline = time.monotonic() + 240
    pending_interaction = None
    while time.monotonic() < deadline:
        interactions = main_runner.ledger.list_codex_interactions(status="pending")
        if interactions:
            pending_interaction = interactions[0]
            break
        if failure_holder:
            break
        if result_holder and result_holder[0]["status"] != "waiting":
            break
        time.sleep(0.1)

    try:
        assert pending_interaction is not None, (
            f"Codex did not request native approval; failures={failure_holder!r}; "
            f"result={result_holder!r}"
        )
        assert pending_interaction["kind"] in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        }
        reply = main_runner.ledger.respond_codex_interaction(
            pending_interaction["id"],
            expected_version=pending_interaction["version"],
            actor="example-reviewer",
            response={"decision": "accept"},
            idempotency_key="native-approval-live-round-trip",
        )
        assert reply["status"] == "replied"
        workflow_thread.join(timeout=240)
        assert not workflow_thread.is_alive()
        assert not failure_holder
        assert result_holder and result_holder[0]["status"] == "waiting"
        assert pending_interaction["delivery_status"] in {"pending", "sent"}
        assert (tmp_path / "approval-probe.txt").read_text().strip() == (
            "authorized write completed"
        )

        run_id = str(result_holder[0]["id"])
        business_request = main_runner.pending_human_requests(run_id)[0]
        finished = main_runner.decide(
            business_request["id"],
            choice="approve",
            comment="Native tool request and business review are separately approved.",
            actor="example-reviewer",
            subject_digest=business_request["subject_digest"],
            expected_version=business_request["version"],
            idempotency_key="native-approval-live-business-review",
        )
        assert finished["status"] == "succeeded"
        assert main_runner.ledger.get_codex_interaction(pending_interaction["id"])[
            "delivery_status"
        ] == "sent"
    finally:
        if workflow_thread.is_alive():
            workflow_thread.join(timeout=5)
        main_runner.close()
