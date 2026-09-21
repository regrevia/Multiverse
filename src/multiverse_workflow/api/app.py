from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.middleware.cors import CORSMiddleware

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"],
    )
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

    @app.get("/api/v1/namespaces/{namespace}/artifacts/{artifact_id}")
    async def get_artifact(
        namespace: str,
        artifact_id: str,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        return _present_artifact(runtime.get_artifact(namespace, artifact_id))

    @app.get("/api/v1/namespaces/{namespace}/artifacts/{artifact_id}/content")
    async def get_artifact_content(
        namespace: str,
        artifact_id: str,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> Response:
        require_scope(principal, "read")
        artifact = runtime.get_artifact(namespace, artifact_id)
        content = runtime.get_artifact_content(namespace, artifact_id)
        return Response(
            content=content,
            media_type=artifact["media_type"],
            headers={"ETag": f'"{artifact["digest"]}"'},
        )

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
        return {"requests": [_present_human_request(request) for request in requests]}

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
        return {
            _camelize_runtime_key(str(key)): _present(item)
            for key, item in value.items()
        }
    return value


def _present_human_request(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": request["id"],
        "runId": request["run_id"],
        "scopeId": request["scope_id"],
        "invocationId": request["invocation_id"],
        "requestType": request["request_type"],
        "title": request["title"],
        "instructions": request["instructions"],
        "input": json.loads(request["input_json"]),
        "inputDigest": request["input_digest"],
        "subjectDigest": request["subject_digest"],
        "choices": json.loads(request["choices_json"]),
        "decisionSchema": json.loads(request["decision_schema_json"]),
        "authorizedSubjects": json.loads(request["authorized_subjects_json"]),
        "createdAt": request["created_at"],
        "expiresAt": request["expires_at"],
        "version": request["version"],
        "status": request["status"],
        "decisionId": request["decision_id"],
        "updatedAt": request["updated_at"],
    }


def _present_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": artifact["id"],
        "namespace": artifact["namespace"],
        "runId": artifact["run_id"],
        "invocationId": artifact["invocation_id"],
        "name": artifact["name"],
        "mediaType": artifact["media_type"],
        "sizeBytes": artifact["size_bytes"],
        "digest": artifact["digest"],
        "status": artifact["status"],
        "createdAt": artifact["created_at"],
    }


_RUNTIME_KEYS = {
    "request_id": "requestId",
    "resource_id": "resourceId",
    "resource_version": "resourceVersion",
    "workflow_id": "workflowId",
    "deployment_id": "deploymentId",
    "package_digest": "packageDigest",
    "binding_digest": "bindingDigest",
    "control_mode": "controlMode",
    "current_scope_id": "currentScopeId",
    "current_node_id": "currentNodeId",
    "current_invocation_id": "currentInvocationId",
    "deadline_at": "deadlineAt",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "rerun_of": "rerunOf",
    "rerun_reason": "rerunReason",
    "scope_id": "scopeId",
    "invocation_id": "invocationId",
    "attempt_id": "attemptId",
    "occurred_at": "occurredAt",
    "subject_digest": "subjectDigest",
    "next_after": "nextAfter",
}


def _camelize_runtime_key(value: str) -> str:
    return _RUNTIME_KEYS.get(value, value)
