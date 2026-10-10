from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.middleware.cors import CORSMiddleware

from multiverse_workflow.runtime.ledger import LedgerConflict
from multiverse_workflow.service.application import RuntimeApplication
from multiverse_workflow.service.contracts import (
    AgentSessionCreateRequest,
    AttemptReconcileRequest,
    CodexInteractionResponseRequest,
    ErrorBody,
    ErrorResponse,
    HumanDecisionRequest,
    NativeSessionBindingRequest,
    RunControlRequest,
    RunCreateRequest,
)
from multiverse_workflow.service.errors import ServiceError

from .dependencies import LocalPrincipal, Scope, ServiceSettings


def create_app(settings: ServiceSettings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            runtime.close()

    app = FastAPI(
        title="Multiverse Runtime Service",
        version="0.1.0",
        lifespan=lifespan,
    )
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

    @app.get("/health/ready", response_model=None)
    async def ready() -> dict[str, Any] | Response:
        report = settings.readiness()
        payload = {
            **report,
            "namespace": settings.namespace,
            "deploymentId": settings.deployment_id,
        }
        if report["status"] != "ready":
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=503, content=payload)
        return payload

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

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}/invocations")
    async def list_invocations(
        namespace: str,
        run_id: str,
        scope_id: str | None = Query(default=None, alias="scopeId"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        invocations = runtime.list_invocations(namespace, run_id, scope_id=scope_id)
        return {"invocations": [_present_invocation(invocation) for invocation in invocations]}

    @app.get("/api/v1/namespaces/{namespace}/invocations/{invocation_id}")
    async def get_invocation(
        namespace: str,
        invocation_id: str,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        return _present_invocation(runtime.get_invocation(namespace, invocation_id))

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

    @app.get("/api/v1/namespaces/{namespace}/human-requests/{request_id}")
    async def get_human_request(
        namespace: str,
        request_id: str,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        return _present_human_request(runtime.get_human_request(namespace, request_id))

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

    @app.get("/api/v1/namespaces/{namespace}/runs/{run_id}/codex-interactions")
    async def list_codex_interactions(
        namespace: str,
        run_id: str,
        status: str | None = None,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        if namespace != principal.namespace:
            raise ServiceError("NOT_FOUND", f"namespace not found: {namespace}", status_code=404)
        interactions = runtime.list_codex_interactions(
            namespace, run_id=run_id, status=status
        )
        return {"interactions": [_present_codex_interaction(item) for item in interactions]}

    @app.get("/api/v1/namespaces/{namespace}/codex-interactions/{interaction_id}")
    async def get_codex_interaction(
        namespace: str,
        interaction_id: str,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        if namespace != principal.namespace:
            raise ServiceError("NOT_FOUND", f"namespace not found: {namespace}", status_code=404)
        return _present_codex_interaction(
            runtime.get_codex_interaction(namespace, interaction_id)
        )

    @app.post(
        "/api/v1/namespaces/{namespace}/codex-interactions/{interaction_id}/responses",
        status_code=202,
    )
    async def respond_codex_interaction(
        namespace: str,
        interaction_id: str,
        payload: CodexInteractionResponseRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "codex:interact")
        if namespace != principal.namespace:
            raise ServiceError("NOT_FOUND", f"namespace not found: {namespace}", status_code=404)
        if idempotency_key is None:
            raise ServiceError(
                "INVALID_ARGUMENT",
                "Idempotency-Key header is required",
                status_code=422,
            )
        interaction = runtime.respond_codex_interaction(
            namespace,
            interaction_id,
            payload,
            idempotency_key=idempotency_key,
            actor=principal.subject,
        )
        return _present_codex_interaction(interaction)

    @app.get("/api/v1/namespaces/{namespace}/agent-sessions")
    async def list_agent_sessions(
        namespace: str,
        run_id: str | None = Query(default=None, alias="runId"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        if namespace != principal.namespace:
            raise ServiceError("NOT_FOUND", f"namespace not found: {namespace}", status_code=404)
        sessions = runtime.runner.ledger.list_agent_sessions(
            namespace, owner_subject=principal.subject, run_id=run_id
        )
        return {"sessions": [_present_agent_session(item) for item in sessions]}

    @app.get("/api/v1/namespaces/{namespace}/agent-sessions/{session_id}")
    async def get_agent_session(
        namespace: str,
        session_id: str,
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "read")
        if namespace != principal.namespace:
            raise ServiceError("NOT_FOUND", f"namespace not found: {namespace}", status_code=404)
        session = runtime.runner.ledger.get_agent_session(
            namespace, session_id, owner_subject=principal.subject
        )
        if session is None:
            raise ServiceError("NOT_FOUND", "agent session not found", status_code=404)
        return _present_agent_session(session)

    @app.post(
        "/api/v1/namespaces/{namespace}/agent-sessions",
        status_code=201,
    )
    async def create_agent_session(
        namespace: str,
        payload: AgentSessionCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "session:manage")
        if namespace != principal.namespace:
            raise ServiceError("NOT_FOUND", f"namespace not found: {namespace}", status_code=404)
        if not idempotency_key:
            raise ServiceError(
                "INVALID_ARGUMENT",
                "Idempotency-Key header is required",
                status_code=422,
            )
        try:
            session = runtime.runner.ledger.create_agent_session(
                namespace=namespace,
                agent_id=payload.agent_id,
                owner_subject=principal.subject,
                scope=payload.scope,
                profile_revision=payload.profile_revision,
                session_id=payload.session_id,
                idempotency_key=idempotency_key,
                run_id=payload.run_id,
                scope_id=payload.scope_id,
                invocation_id=payload.invocation_id,
            )
        except LedgerConflict as exc:
            raise ServiceError("STATE_CONFLICT", str(exc), status_code=409) from exc
        return _present_agent_session(session)

    @app.post(
        "/api/v1/namespaces/{namespace}/agent-sessions/{session_id}/native-bindings",
        status_code=201,
    )
    async def bind_native_session(
        namespace: str,
        session_id: str,
        payload: NativeSessionBindingRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: LocalPrincipal = Depends(authorize),  # noqa: B008
    ) -> dict[str, Any]:
        require_scope(principal, "session:manage")
        if namespace != principal.namespace:
            raise ServiceError("NOT_FOUND", f"namespace not found: {namespace}", status_code=404)
        if not idempotency_key:
            raise ServiceError(
                "INVALID_ARGUMENT",
                "Idempotency-Key header is required",
                status_code=422,
            )
        if runtime.runner.ledger.get_agent_session(
            namespace, session_id, owner_subject=principal.subject
        ) is None:
            raise ServiceError("NOT_FOUND", "agent session not found", status_code=404)
        try:
            binding = runtime.runner.ledger.bind_native_session(
                session_id,
                expected_version=payload.expected_version,
                provider_id=payload.provider_id,
                installation_id=payload.installation_id,
                storage_id=payload.storage_id,
                native_session_id=payload.native_session_id,
                provider_version=payload.provider_version,
                capabilities=payload.capabilities,
                source=payload.source,
                workspace_revision=payload.workspace_revision,
                policy_revision=payload.policy_revision,
                idempotency_key=idempotency_key,
            )
        except LedgerConflict as exc:
            raise ServiceError("STATE_CONFLICT", str(exc), status_code=409) from exc
        return _present_native_session_binding(binding)

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


def _present_codex_interaction(interaction: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": interaction["id"],
        "runId": interaction["run_id"],
        "scopeId": interaction["scope_id"],
        "invocationId": interaction["invocation_id"],
        "attemptId": interaction["attempt_id"],
        "nativeRequestId": interaction["native_request_id"],
        "threadId": interaction["thread_id"],
        "turnId": interaction["turn_id"],
        "kind": interaction["kind"],
        "payload": json.loads(interaction["payload_json"]),
        "authorizedSubjects": json.loads(interaction["authorized_subjects_json"]),
        "expiresAt": interaction["expires_at"],
        "version": interaction["version"],
        "status": interaction["status"],
        "deliveryStatus": interaction["delivery_status"],
        "invalidReason": interaction["invalid_reason"],
        "response": (
            json.loads(interaction["response_json"])
            if interaction["response_json"] is not None
            else None
        ),
        "actor": interaction["actor"],
        "createdAt": interaction["created_at"],
        "updatedAt": interaction["updated_at"],
    }


def _present_agent_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": session["id"],
        "namespace": session["namespace"],
        "agentId": session["agent_id"],
        "ownerSubject": session["owner_subject"],
        "scope": session["scope"],
        "profileRevision": session["profile_revision"],
        "runId": session["run_id"],
        "scopeId": session["scope_id"],
        "invocationId": session["invocation_id"],
        "activeBindingId": session["active_binding_id"],
        "version": session["version"],
        "status": session["status"],
        "bindings": [
            _present_native_session_binding(binding)
            for binding in session["bindings"]
        ],
        "createdAt": session["created_at"],
        "updatedAt": session["updated_at"],
    }


def _present_native_session_binding(binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": binding["id"],
        "agentSessionId": binding["agent_session_id"],
        "providerId": binding["provider_id"],
        "installationId": binding["installation_id"],
        "storageId": binding["storage_id"],
        "nativeSessionId": binding["native_session_id"],
        "providerVersion": binding["provider_version"],
        "capabilities": binding["capabilities"],
        "source": binding["source"],
        "workspaceRevision": binding["workspace_revision"],
        "policyRevision": binding["policy_revision"],
        "status": binding["status"],
        "createdAt": binding["created_at"],
        "updatedAt": binding["updated_at"],
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


def _present_invocation(invocation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": invocation["id"],
        "runId": invocation["run_id"],
        "scopeId": invocation["scope_id"],
        "nodeId": invocation["node_id"],
        "status": invocation["status"],
        "input": invocation["input"],
        "inputDigest": invocation["input_digest"],
        "output": invocation["output"],
        "error": invocation["error"],
        "version": invocation["version"],
        "createdAt": invocation["created_at"],
        "updatedAt": invocation["updated_at"],
        "attempts": [
            {
                "id": attempt["id"],
                "attemptNo": attempt["attempt_no"],
                "status": attempt["status"],
                "version": attempt["version"],
                "inputDigest": attempt["input_digest"],
                "externalRef": attempt["external_ref"],
                "output": attempt["output"],
                "error": attempt["error"],
                "createdAt": attempt["created_at"],
                "updatedAt": attempt["updated_at"],
            }
            for attempt in invocation["attempts"]
        ],
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
