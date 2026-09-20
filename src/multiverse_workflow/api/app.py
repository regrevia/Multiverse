from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from multiverse_workflow.service.contracts import (
    ErrorBody,
    ErrorResponse,
    HumanDecisionRequest,
    RunControlRequest,
    RunCreateRequest,
)
from multiverse_workflow.service.errors import ServiceError

from .dependencies import ServiceSettings


def create_app(settings: ServiceSettings) -> FastAPI:
    app = FastAPI(title="Multiverse Runtime Service", version="0.1.0")
    runtime = settings.create_application()
    app.state.settings = settings
    app.state.runtime = runtime

    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(code=exc.code, message=exc.message, details=exc.details)
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(mode="json", by_alias=True),
        )

    async def authorize(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> None:
        token = settings.bearer_token
        if token is None:
            return
        if authorization != f"Bearer {token}":
            raise ServiceError("UNAUTHORIZED", "valid bearer token required", status_code=401)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready(_: None = Depends(authorize)) -> dict[str, str]:
        return {
            "status": "ready",
            "databasePath": str(settings.database_path.expanduser().resolve()),
            "namespace": settings.namespace,
        }

    @app.post("/api/v1/namespaces/{namespace}/runs", status_code=202)
    async def create_run(
        namespace: str,
        payload: RunCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        if idempotency_key is None:
            raise ServiceError(
                "INVALID_ARGUMENT",
                "Idempotency-Key header is required",
                status_code=422,
            )
        receipt = runtime.create_run(
            payload.model_copy(update={"namespace": namespace}),
            idempotency_key=idempotency_key,
        )
        return receipt.model_dump(mode="json", by_alias=True)

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}")
    async def get_run(
        namespace: str,
        run_id: str,
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        return cast(dict[str, Any], _present(runtime.get_run(namespace, run_id)))

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}/graph")
    async def get_graph(
        namespace: str,
        run_id: str,
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        return cast(dict[str, Any], _present(runtime.get_graph(namespace, run_id)))

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}/events")
    async def list_events(
        namespace: str,
        run_id: str,
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        events = runtime.list_events(namespace, run_id, after=after, limit=limit)
        return {"events": _present(events), "nextAfter": events[-1]["seq"] if events else after}

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}/stream")
    async def stream_events(
        namespace: str,
        run_id: str,
        after: int = Query(default=0, ge=0),
        _: None = Depends(authorize),
    ) -> StreamingResponse:
        runtime.get_run(namespace, run_id)

        async def event_stream() -> AsyncIterator[str]:
            cursor = after
            idle = 0.0
            while idle < settings.sse_idle_timeout:
                events = runtime.list_events(namespace, run_id, after=cursor, limit=100)
                if events:
                    for event in events:
                        cursor = int(event["seq"])
                        yield _sse_event(event)
                    idle = 0.0
                    continue
                await asyncio.sleep(settings.sse_poll_interval)
                idle += settings.sse_poll_interval
            yield ": keepalive\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v1/namespaces/{namespace}/runs/{run_id}:pause", status_code=202)
    async def pause_run(
        namespace: str,
        run_id: str,
        payload: RunControlRequest,
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        return runtime.control_run(namespace, run_id, "pause", payload).model_dump(
            mode="json", by_alias=True
        )

    @app.post("/api/v1/namespaces/{namespace}/runs/{run_id}:resume", status_code=202)
    async def resume_run(
        namespace: str,
        run_id: str,
        payload: RunControlRequest,
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        return runtime.control_run(namespace, run_id, "resume", payload).model_dump(
            mode="json", by_alias=True
        )

    @app.post("/api/v1/namespaces/{namespace}/runs/{run_id}:cancel", status_code=202)
    async def cancel_run(
        namespace: str,
        run_id: str,
        payload: RunControlRequest,
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        return runtime.control_run(namespace, run_id, "cancel", payload).model_dump(
            mode="json", by_alias=True
        )

    @app.get("/api/v1/namespaces/{namespace}/human-requests")
    async def list_human_requests(
        namespace: str,
        run_id: str | None = Query(default=None, alias="runId"),
        status: str | None = None,
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        requests = runtime.list_human_requests(namespace, run_id=run_id, status=status)
        return {"requests": _present(requests)}

    @app.post(
        "/api/v1/namespaces/{namespace}/human-requests/{request_id}/decisions",
        status_code=202,
    )
    async def decide_human_request(
        namespace: str,
        request_id: str,
        payload: HumanDecisionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _: None = Depends(authorize),
    ) -> dict[str, Any]:
        if idempotency_key is None:
            raise ServiceError(
                "INVALID_ARGUMENT",
                "Idempotency-Key header is required",
                status_code=422,
            )
        receipt = runtime.decide_human_request(
            namespace,
            request_id,
            payload,
            idempotency_key=idempotency_key,
        )
        return receipt.model_dump(mode="json", by_alias=True)

    return app


def _sse_event(event: dict[str, Any]) -> str:
    return (
        f"id: {event['seq']}\n"
        f"event: {event['type']}\n"
        f"data: {json.dumps(_present(event), ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _present(value: Any) -> Any:
    if isinstance(value, list):
        return [_present(item) for item in value]
    if isinstance(value, dict):
        return {_camelize(str(key)): _present(item) for key, item in value.items()}
    return value


def _camelize(value: str) -> str:
    return re.sub(r"_([a-z])", lambda match: match.group(1).upper(), value)
