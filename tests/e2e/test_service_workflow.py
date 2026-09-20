from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from multiverse_workflow.api.app import create_app
from multiverse_workflow.api.dependencies import ServiceSettings

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "presets/content-delivery"
BINDING = ROOT / "examples/bindings/content-local.yaml"


@pytest.mark.anyio
async def test_http_workflow_survives_client_disconnect(tmp_path: Path) -> None:
    application = create_app(
        ServiceSettings(
            database_path=tmp_path / "runtime.db",
            package_dir=PACKAGE,
            binding_path=BINDING,
            bearer_token="test-token",
            subject="example-reviewer",
            sse_idle_timeout=0.01,
            sse_poll_interval=0.001,
        )
    )

    create_transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(
        transport=create_transport,
        base_url="http://test",
    ) as client:
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

    decide_transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(
        transport=decide_transport,
        base_url="http://test",
    ) as client:
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
                "comment": "Approved after reconnecting.",
            },
        )
        finished = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}",
            headers={"Authorization": "Bearer test-token"},
        )

        assert decided.status_code == 202
        assert finished.json()["id"] == run_id
        assert finished.json()["status"] == "waiting"

    application.state.runtime.runner.sweep(worker_id="test-worker")
    assert application.state.runtime.runner.ledger.get_run(run_id)["status"] == "succeeded"
