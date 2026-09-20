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
        sse_poll_interval=0.001,
        sse_idle_timeout=0.01,
    )


@pytest.mark.anyio
async def test_health_and_run_projection_endpoints(settings: ServiceSettings) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/health/live")).json() == {"status": "ok"}
        ready = await client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        created = await client.post(
            "/api/v1/namespaces/local/runs",
            headers={"Idempotency-Key": "create-1"},
            json={
                "package": str(PACKAGE),
                "binding": str(BINDING),
                "workflow": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        assert created.status_code == 202
        run_id = created.json()["resourceId"]

        loaded = await client.get(f"/api/v1/namespaces/local/runs/{run_id}")
        assert loaded.status_code == 200
        assert loaded.json()["id"] == run_id
        assert loaded.json()["status"] == "waiting"

        graph = await client.get(f"/api/v1/namespaces/local/runs/{run_id}/graph")
        assert graph.status_code == 200
        assert graph.json()["run"]["id"] == run_id
        assert graph.json()["nodes"]

        events = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/events?after=0"
        )
        assert events.status_code == 200
        assert [event["seq"] for event in events.json()["events"]] == list(
            range(1, len(events.json()["events"]) + 1)
        )


@pytest.mark.anyio
async def test_stale_control_returns_json_state_conflict(settings: ServiceSettings) -> None:
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/namespaces/local/runs",
            headers={"Idempotency-Key": "create-1"},
            json={
                "package": str(PACKAGE),
                "binding": str(BINDING),
                "workflow": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        run_id = created.json()["resourceId"]
        response = await client.post(
            f"/api/v1/namespaces/local/runs/{run_id}:pause",
            headers={"Idempotency-Key": "pause-1"},
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
            headers={"Idempotency-Key": "create-1"},
            json={
                "package": str(PACKAGE),
                "binding": str(BINDING),
                "workflow": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        run_id = created.json()["resourceId"]

        response = await client.get(
            f"/api/v1/namespaces/local/runs/{run_id}/stream?after=0"
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
            headers={"Idempotency-Key": "create-1"},
            json={
                "package": str(PACKAGE),
                "binding": str(BINDING),
                "workflow": "delivery",
                "input": {"goal": "write a release note"},
            },
        )
        run_id = created.json()["resourceId"]
        requests = await client.get(
            f"/api/v1/namespaces/local/human-requests?runId={run_id}"
        )
        request = requests.json()["requests"][0]

        decided = await client.post(
            f"/api/v1/namespaces/local/human-requests/{request['id']}/decisions",
            headers={"Idempotency-Key": "decision-1"},
            json={
                "expectedVersion": request["version"],
                "subjectDigest": request["subjectDigest"],
                "actor": "example-reviewer",
                "choice": "approve",
                "comment": "Approved.",
            },
        )
        assert decided.status_code == 202

        finished = await client.get(f"/api/v1/namespaces/local/runs/{run_id}")
        assert finished.json()["status"] == "succeeded"
