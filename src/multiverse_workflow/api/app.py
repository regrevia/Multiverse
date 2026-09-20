from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from multiverse_workflow.service.application import RuntimeApplication
from multiverse_workflow.service.contracts import (
    AttemptReconcileRequest,
    ErrorBody,
    ErrorResponse,
    HumanDecisionRequest,
    RunControlRequest,
    RunCreateRequest,
)
from multiverse_workflow.service.errors import ServiceError

from .dependencies import LocalPrincipal, Scope, ServiceSettings


def create_app(settings: ServiceSettings) -> FastAPI:
    app = FastAPI(title="Multiverse Runtime Service", version="0.1.0")
    runtime = settings.create_application()
    app.state.settings = settings
    app.state.runtime = runtime

    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
                evidenceRefs=exc.evidence_refs,
                nextActions=exc.next_actions,
            ),
            requestId=exc.request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(mode="json", by_alias=True),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(
                code="INVALID_ARGUMENT",
                message="request validation failed",
                details={"errors": exc.errors()},
            ),
            requestId=f"req_{id(exc):x}",
        )
        return JSONResponse(
            status_code=422,
            content=body.model_dump(mode="json", by_alias=True),
        )

    async def authorize(
        authorization: str | None = Header(default=None),
    ) -> LocalPrincipal:
        if authorization != f"Bearer {settings.bearer_token}":
            raise ServiceError("UNAUTHORIZED", "valid bearer token required", status_code=401)
        return LocalPrincipal(
            subject=settings.subject,
            namespace=settings.namespace,
            scopes=settings.scopes,
        )

    def require_scope(principal: LocalPrincipal, scope: Scope) -> None:
        if scope not in principal.scopes:
            raise ServiceError(
                "PERMISSION_DENIED",
                f"scope is required: {scope}",
                status_code=403,
            )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {
            "status": "ready",
            "databasePath": str(settings.database_path.expanduser().resolve()),
            "namespace": settings.namespace,
            "deploymentId": settings.deployment_id,
        }

    @app.post("/api/v1/namespaces/{namespace}/runs", status_code=202)
    async def create_run(
        namespace: str,
        payload: RunCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "run:start")
        if namespace != principal.namespace:
            raise ServiceError("NOT_FOUND", f"namespace not found: {namespace}", status_code=404)
        if idempotency_key is None:
            raise ServiceError(
                "INVALID_ARGUMENT",
                "Idempotency-Key header is required",
                status_code=422,
            )
        receipt = runtime.create_run(payload, idempotency_key=idempotency_key)
        return receipt.model_dump(mode="json", by_alias=True)

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}")
    async def get_run(
        namespace: str,
        run_id: str,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        return cast(dict[str, Any], _present(runtime.get_run(namespace, run_id)))

    @app.post(
        "/api/v1/namespaces/{namespace}/attempts/{attempt_id}:reconcile",
        status_code=202,
    )
    async def reconcile_attempt(
        namespace: str,
        attempt_id: str,
        payload: AttemptReconcileRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "reconcile:write")
        if namespace != principal.namespace:
            raise ServiceError("NOT_FOUND", f"namespace not found: {namespace}", status_code=404)
        if idempotency_key is None:
            raise ServiceError(
                "INVALID_ARGUMENT",
                "Idempotency-Key header is required",
                status_code=422,
            )
        receipt = runtime.reconcile_attempt(
            namespace,
            attempt_id,
            payload,
            idempotency_key=idempotency_key,
        )
        return receipt.model_dump(mode="json", by_alias=True)

    @app.get("/api/v1/commands/{command_id}")
    async def get_command(
        command_id: str,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        return cast(dict[str, Any], _present(runtime.get_command(principal.namespace, command_id)))

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}/graph")
    async def get_graph(
        namespace: str,
        run_id: str,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        return cast(dict[str, Any], _present(runtime.get_graph(namespace, run_id)))

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}/events")
    async def list_events(
        namespace: str,
        run_id: str,
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        events = runtime.list_events(namespace, run_id, after=after, limit=limit)
        return {"events": _present(events), "nextAfter": events[-1]["seq"] if events else after}

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}/stream")
    async def stream_events(
        namespace: str,
        run_id: str,
        after: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> StreamingResponse:
        require_scope(principal, "read")
        runtime.get_run(namespace, run_id)
        if last_event_id is not None:
            try:
                after = int(last_event_id)
            except ValueError as exc:
                raise ServiceError(
                    "INVALID_ARGUMENT",
                    "Last-Event-ID must be an integer event sequence",
                    status_code=400,
                ) from exc

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
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "run:control")
        return _control_response(
            runtime,
            namespace,
            run_id,
            "pause",
            payload,
            idempotency_key,
        )

    @app.post("/api/v1/namespaces/{namespace}/runs/{run_id}:resume", status_code=202)
    async def resume_run(
        namespace: str,
        run_id: str,
        payload: RunControlRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "run:control")
        return _control_response(
            runtime,
            namespace,
            run_id,
            "resume",
            payload,
            idempotency_key,
        )

    @app.post("/api/v1/namespaces/{namespace}/runs/{run_id}:cancel", status_code=202)
    async def cancel_run(
        namespace: str,
        run_id: str,
        payload: RunControlRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "run:control")
        return _control_response(
            runtime,
            namespace,
            run_id,
            "cancel",
            payload,
            idempotency_key,
        )

    @app.get("/api/v1/namespaces/{namespace}/human-requests")
    async def list_human_requests(
        namespace: str,
        run_id: str | None = Query(default=None, alias="runId"),
        status: str | None = None,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
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
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "human:decide")
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


def _control_response(
    runtime: RuntimeApplication,
    namespace: str,
    run_id: str,
    operation: str,
    payload: RunControlRequest,
    idempotency_key: str | None,
) -> dict[str, Any]:
    if idempotency_key is None:
        raise ServiceError(
            "INVALID_ARGUMENT",
            "Idempotency-Key header is required",
            status_code=422,
        )
    receipt = runtime.control_run(
        namespace,
        run_id,
        operation,  # type: ignore[arg-type]
        payload,
        idempotency_key=idempotency_key,
    )
    return receipt.model_dump(mode="json", by_alias=True)


def _present(value: Any) -> Any:
    if isinstance(value, list):
        return [_present(item) for item in value]
    if isinstance(value, dict):
        return {_camelize(str(key)): _present(item) for key, item in value.items()}
    return value


def _camelize(value: str) -> str:
    return re.sub(r"_([a-z])", lambda match: match.group(1).upper(), value)
