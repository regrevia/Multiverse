from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from multiverse_workflow.api.app import create_app
from multiverse_workflow.api.dependencies import ServiceSettings

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "presets/content-delivery"
BINDING = ROOT / "examples/bindings/content-local.yaml"


@pytest.fixture
def settings(tmp_path: Path) -> ServiceSettings:
    return ServiceSettings(
        database_path=tmp_path / "runtime.db",
        package_dir=PACKAGE,
        binding_path=BINDING,
        bearer_token="test-token",
        subject="example-reviewer",
        sse_poll_interval=0.001,
        sse_idle_timeout=0.01,
    )


@pytest.mark.anyio
async def test_health_and_run_projection_endpoints(settings: ServiceSettings) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "create-1",
        }
        assert (await client.get("/health/live")).json() == {"status": "ok"}
        ready = await client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"
        assert ready.json()["profile"] == "personal"
        assert ready.json()["databaseBackend"] == "sqlite"
        assert ready.json()["runtimeBackend"] == "sqlite-ledger"
        assert ready.json()["scheduler"] == "local-single-active"
        assert ready.json()["capabilities"]["workflowLedger"] is True
        assert ready.json()["capabilities"]["postgresRuntime"] is False
        assert ready.json()["capabilities"]["localArtifactBytes"] is True
        assert ready.json()["capabilities"]["serviceArtifactBytes"] is False
        assert ready.json()["checks"]["database"]["status"] == "ready"
        assert ready.json()["checks"]["artifactStorage"]["status"] == "ready"
        assert "test-token" not in ready.text

        created = await client.post(
            "/api/v1/namespaces/local/runs",
            headers=headers,
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        assert created.status_code == 202
        run_id = created.json()["resourceId"]
        application.state.runtime.runner.sweep(worker_id="test-worker")

        loaded = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}",
            headers={"Authorization": "Bearer test-token"},
        )
        assert loaded.status_code == 200
        assert loaded.json()["id"] == run_id
        assert loaded.json()["status"] == "waiting"

        graph = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/graph",
            headers={"Authorization": "Bearer test-token"},
        )
        assert graph.status_code == 200
        assert graph.json()["run"]["id"] == run_id
        assert graph.json()["nodes"]

        events = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/events?after=0",
            headers={"Authorization": "Bearer test-token"},
        )
        assert events.status_code == 200
        assert [event["seq"] for event in events.json()["events"]] == list(
            range(1, len(events.json()["events"]) + 1)
        )


@pytest.mark.anyio
async def test_health_ready_returns_503_when_runtime_database_disappears(
    settings: ServiceSettings,
) -> None:
    application = create_app(settings)
    settings.database_path.unlink()
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["namespace"] == "local"
    assert response.json()["deploymentId"] == "deployment_local"
    application.state.runtime.close()


@pytest.mark.anyio
async def test_invocation_and_human_request_read_endpoints_are_namespace_scoped(
    settings: ServiceSettings,
) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "read-endpoints",
            },
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        run_id = created.json()["resourceId"]
        application.state.runtime.runner.sweep(worker_id="read-endpoints-worker")
        invocation = application.state.runtime.runner.ledger.list_invocations(run_id)[0]
        request = application.state.runtime.runner.ledger.list_human_requests(
            run_id=run_id,
        )[0]

        invocations = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/invocations",
            headers={"Authorization": "Bearer test-token"},
        )
        invocation_detail = await client.get(
            f"/api/v1/namespaces/local/invocations/{invocation['id']}",
            headers={"Authorization": "Bearer test-token"},
        )
        human_request = await client.get(
            f"/api/v1/namespaces/local/human-requests/{request['id']}",
            headers={"Authorization": "Bearer test-token"},
        )
        hidden_invocation = await client.get(
            f"/api/v1/namespaces/other/invocations/{invocation['id']}",
            headers={"Authorization": "Bearer test-token"},
        )

    assert invocations.status_code == 200
    assert invocations.json()["invocations"][0]["id"] == invocation["id"]
    assert invocations.json()["invocations"][0]["runId"] == run_id
    assert "dispatchKey" not in invocations.json()["invocations"][0]["attempts"][0]
    assert invocation_detail.status_code == 200
    assert invocation_detail.json()["id"] == invocation["id"]
    assert invocation_detail.json()["input"] == {"goal": "write a release note"}
    assert human_request.status_code == 200
    assert human_request.json()["id"] == request["id"]
    assert human_request.json()["subjectDigest"] == request["subject_digest"]
    assert hidden_invocation.status_code == 404


@pytest.mark.anyio
async def test_codex_interaction_read_and_reply_require_runtime_identity(
    settings: ServiceSettings,
) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "codex-interaction-run",
            },
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        run_id = created.json()["resourceId"]
        application.state.runtime.runner.sweep(worker_id="interaction-api")
        runner = application.state.runtime.runner
        invocation = next(
            item
            for item in runner.ledger.list_invocations(run_id)
            if item["node_id"] == "produce"
        )
        attempt = runner.ledger.latest_attempt(invocation["id"])
        interaction = runner.ledger.create_codex_interaction(
            run_id=run_id,
            scope_id=invocation["scope_id"],
            invocation_id=invocation["id"],
            attempt_id=attempt["id"],
            native_request_id="native-api-1",
            thread_id="thread-1",
            turn_id="turn-1",
            kind="item/commandExecution/requestApproval",
            payload={"threadId": "thread-1", "turnId": "turn-1", "command": "pytest"},
            authorized_subjects=["example-reviewer"],
            expires_at="2099-01-01T00:00:00Z",
        )
        auth = {"Authorization": "Bearer test-token"}
        listed = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/codex-interactions",
            headers=auth,
        )
        response_url = (
            f"/api/v1/namespaces/local/codex-interactions/{interaction['id']}/responses"
        )
        replied = await client.post(
            response_url,
            headers={**auth, "Idempotency-Key": "native-api-reply"},
            json={
                "expectedVersion": 1,
                "response": {"decision": "accept"},
            },
        )
        stale = await client.post(
            response_url,
            headers={**auth, "Idempotency-Key": "native-api-reply-conflict"},
            json={
                "expectedVersion": 1,
                "response": {"decision": "decline"},
            },
        )

    assert listed.status_code == 200
    assert listed.json()["interactions"][0]["nativeRequestId"] == "native-api-1"
    assert listed.json()["interactions"][0]["deliveryStatus"] == "not_sent"
    assert replied.status_code == 202
    assert replied.json()["status"] == "replied"
    assert stale.status_code == 409


@pytest.mark.anyio
async def test_codex_interaction_api_is_versioned_idempotent_and_subject_authorized(
    settings: ServiceSettings,
) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "codex-interaction-run",
            },
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        run_id = created.json()["resourceId"]
        application.state.runtime.runner.sweep(worker_id="interaction-test")
        runner = application.state.runtime.runner
        invocation = next(
            item
            for item in runner.ledger.list_invocations(run_id)
            if item["node_id"] == "produce"
        )
        attempt = runner.ledger.latest_attempt(invocation["id"])
        scope = runner.ledger.get_scope(invocation["scope_id"])
        interaction = runner.ledger.create_codex_interaction(
            run_id=run_id,
            scope_id=scope["id"],
            invocation_id=invocation["id"],
            attempt_id=attempt["id"],
            native_request_id="native-request-1",
            thread_id="thread-1",
            turn_id="turn-1",
            kind="item/commandExecution/requestApproval",
            payload={"threadId": "thread-1", "turnId": "turn-1", "command": "ls"},
            authorized_subjects=["example-reviewer"],
            expires_at="2099-01-01T00:00:00Z",
        )

        listed = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/codex-interactions",
            headers={"Authorization": "Bearer test-token"},
        )
        response_url = (
            f"/api/v1/namespaces/local/codex-interactions/{interaction['id']}/responses"
        )
        response_headers = {
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "native-response-1",
        }
        response_body = {
            "expectedVersion": interaction["version"],
            "response": {"decision": "accept"},
        }
        replied = await client.post(response_url, headers=response_headers, json=response_body)
        replay = await client.post(response_url, headers=response_headers, json=response_body)
        conflict = await client.post(
            response_url,
            headers=response_headers,
            json={
                "expectedVersion": interaction["version"],
                "response": {"decision": "decline"},
            },
        )

    assert listed.status_code == 200
    assert listed.json()["interactions"][0]["id"] == interaction["id"]
    assert replied.status_code == 202
    assert replied.json()["status"] == "replied"
    assert replay.status_code == 202
    assert replay.json()["response"] == {"decision": "accept"}
    assert conflict.status_code == 409


@pytest.mark.anyio
async def test_runtime_allows_local_inspector_origin(settings: ServiceSettings) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health/live",
            headers={"Origin": "http://127.0.0.1:4173"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:4173"


@pytest.mark.anyio
async def test_event_payload_keys_are_not_camelized_or_overwritten(
    settings: ServiceSettings,
) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "create-1",
            },
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        run_id = created.json()["resourceId"]
        application.state.runtime.runner.ledger.record_event(
            run_id,
            "business.payload",
            {"customer_id": "snake", "customerId": "camel"},
        )

        events = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/events?after=0",
            headers={"Authorization": "Bearer test-token"},
        )

    payload = next(
        event["payload"]
        for event in events.json()["events"]
        if event["type"] == "business.payload"
    )
    assert payload == {"customer_id": "snake", "customerId": "camel"}


@pytest.mark.anyio
async def test_stale_control_returns_json_state_conflict(settings: ServiceSettings) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "create-1",
            },
        )
        run_id = created.json()["resourceId"]
        application.state.runtime.runner.sweep(worker_id="test-worker")
        response = await client.post(
            f"/api/v1/namespaces/local/runs/{run_id}:pause",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "pause-1",
            },
            json={"expectedVersion": 1, "reason": "Pause for review."},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "STATE_CONFLICT"


@pytest.mark.anyio
async def test_sse_replays_events_with_sequence_ids(settings: ServiceSettings) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "create-1",
            },
        )
        run_id = created.json()["resourceId"]

        response = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/stream?after=0",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        ids = [
            int(line.removeprefix("id: "))
            for line in response.text.splitlines()
            if line.startswith("id: ")
        ]
        assert ids == list(range(1, len(ids) + 1))
        assert any(
            json.loads(line.removeprefix("data: "))["type"] == "run.created"
            for line in response.text.splitlines()
            if line.startswith("data: ")
        )


@pytest.mark.anyio
async def test_human_request_can_be_decided_over_http(settings: ServiceSettings) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "create-1",
            },
        )
        run_id = created.json()["resourceId"]
        application.state.runtime.runner.sweep(worker_id="test-worker")
        requests = await client.get(
            f"/api/v1/namespaces/local/human-requests?runId={run_id}",
            headers={"Authorization": "Bearer test-token"},
        )
        request = requests.json()["requests"][0]

        decided = await client.post(
            f"/api/v1/namespaces/local/human-requests/{request['id']}/decisions",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "decision-1",
            },
            json={
                "expectedVersion": request["version"],
                "subjectDigest": request["subjectDigest"],
                "choice": "approve",
                "comment": "Approved.",
            },
        )
        assert decided.status_code == 202

        finished = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}",
            headers={"Authorization": "Bearer test-token"},
        )
        assert finished.json()["status"] == "waiting"
        application.state.runtime.runner.sweep(worker_id="test-worker")
        finished = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}",
            headers={"Authorization": "Bearer test-token"},
        )
        assert finished.json()["status"] == "succeeded"


@pytest.mark.anyio
async def test_authorized_artifact_metadata_and_content_can_be_read_over_http(
    settings: ServiceSettings,
    tmp_path: Path,
) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    source = tmp_path / "release.md"
    source.write_text("# Release\n", encoding="utf-8")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "create-artifact-read",
            },
        )
        run_id = created.json()["resourceId"]
        artifact = application.state.runtime.runner.ledger.register_artifact(
            run_id=run_id,
            source_path=source,
            name="release.md",
            media_type="text/markdown",
        )

        metadata = await client.get(
            f"/api/v1/namespaces/local/artifacts/{artifact['id']}",
            headers={"Authorization": "Bearer test-token"},
        )
        content = await client.get(
            f"/api/v1/namespaces/local/artifacts/{artifact['id']}/content",
            headers={"Authorization": "Bearer test-token"},
        )

    assert metadata.status_code == 200
    assert metadata.json() == {
        "id": artifact["id"],
        "namespace": "local",
        "runId": run_id,
        "invocationId": None,
        "name": "release.md",
        "mediaType": "text/markdown",
        "sizeBytes": len(b"# Release\n"),
        "digest": artifact["digest"],
        "status": "ready",
        "createdAt": artifact["created_at"],
    }
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("text/markdown")
    assert content.headers["etag"] == f'"{artifact["digest"]}"'
    assert content.content == b"# Release\n"


@pytest.mark.anyio
async def test_artifact_read_does_not_leak_across_namespaces(
    settings: ServiceSettings,
    tmp_path: Path,
) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    source = tmp_path / "release.md"
    source.write_text("# Release\n", encoding="utf-8")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "create-artifact-namespace",
            },
        )
        run_id = created.json()["resourceId"]
        artifact = application.state.runtime.runner.ledger.register_artifact(
            run_id=run_id,
            source_path=source,
            name="release.md",
            media_type="text/markdown",
        )
        response = await client.get(
            f"/api/v1/namespaces/other/artifacts/{artifact['id']}",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.anyio
async def test_command_can_be_queried_after_create(settings: ServiceSettings) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "create-1",
            },
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        command = await client.get(
            f"/api/v1/commands/{created.json()['requestId']}",
            headers={"Authorization": "Bearer test-token"},
        )

    assert command.status_code == 200
    assert command.json()["requestId"] == created.json()["requestId"]
    assert command.json()["status"] == "completed"


@pytest.mark.anyio
async def test_run_create_rejects_a_namespace_different_from_authenticated_subject(
    settings: ServiceSettings,
) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/namespaces/other/runs",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "create-other",
            },
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.anyio
async def test_attempt_reconcile_uses_authenticated_subject_and_persistent_receipt(
    settings: ServiceSettings,
) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "create-1",
            },
            json={
                "deploymentId": "deployment_local",
                "workflowId": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        run_id = created.json()["resourceId"]
        application.state.runtime.runner.sweep(worker_id="test-worker")
        invocation = application.state.runtime.runner.ledger.list_invocations(run_id)[-1]
        attempt = application.state.runtime.runner.ledger.latest_attempt(invocation["id"])
        assert attempt is not None
        unknown = application.state.runtime.runner.ledger.finish_attempt(
            attempt["id"],
            status="unknown",
        )
        response = await client.post(
            f"/api/v1/namespaces/local/attempts/{unknown['id']}:reconcile",
            headers={
                "Authorization": "Bearer test-token",
                "Idempotency-Key": "reconcile-1",
            },
            json={
                "expectedVersion": unknown["version"],
                "conclusion": "confirmed_failed",
                "evidenceRefs": ["evidence://provider/failed"],
                "reason": "The provider confirmed the execution failed.",
            },
        )

        assert response.status_code == 202
        command = await client.get(
            f"/api/v1/commands/{response.json()['requestId']}",
            headers={"Authorization": "Bearer test-token"},
        )

    assert command.status_code == 200
    assert command.json()["status"] == "completed"
    reconciled = application.state.runtime.runner.ledger.get_attempt(unknown["id"])
    assert reconciled is not None
    assert '"actor": "example-reviewer"' in reconciled["reconciliation_json"]
    assert application.state.runtime.runner.ledger.get_run(run_id)["status"] == (
        "blocked"
    )
    reconciliation_wait = application.state.runtime.runner.ledger.get_wait_by_key(
        "local", f"attempt-reconcile:{unknown['id']}"
    )
    assert reconciliation_wait is not None
    assert reconciliation_wait["status"] == "pending"
    application.state.runtime.runner.sweep(worker_id="test-worker")
    assert application.state.runtime.runner.ledger.get_run(run_id)["status"] == (
        "failed"
    )
