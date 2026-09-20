from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from multiverse_workflow.runtime.ledger import Ledger


def build_run_projection(ledger: Ledger, run_id: str) -> dict[str, Any]:
    """Build a read-only Inspector DTO from one persisted Run."""
    run = ledger.get_run(run_id)
    if run is None:
        raise KeyError(f"run not found: {run_id}")
    plan = json.loads(run["plan_json"])
    scopes = ledger.list_scopes(run_id)
    invocations = ledger.list_invocations(run_id)
    attempts = ledger.list_attempts(run_id)
    invocations_by_scope_node = {
        (invocation["scope_id"], invocation["node_id"]): invocation
        for invocation in invocations
    }
    attempts_by_invocation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        attempts_by_invocation[attempt["invocation_id"]].append(attempt)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for scope in scopes:
        scope_plan = _scope_plan(plan, scope["workflow_id"])
        for node_id, definition in scope_plan["nodes"].items():
            invocation = invocations_by_scope_node.get((scope["id"], node_id))
            nodes.append(
                {
                    "id": f"{scope['id']}:{node_id}",
                    "scopeId": scope["id"],
                    "nodeId": node_id,
                    "title": definition["definition"].get("title", node_id),
                    "type": _node_type(definition, invocation),
                    "status": _node_status(scope, invocation),
                    "invocation": _invocation_summary(invocation),
                    "latestAttempt": _latest_attempt_summary(
                        attempts_by_invocation.get(invocation["id"], [])
                        if invocation is not None
                        else []
                    ),
                }
            )
        for edge in scope_plan["edges"]:
            edges.append(
                {
                    "id": f"{scope['id']}:{edge['from']}->{edge['to']}",
                    "scopeId": scope["id"],
                    "from": f"{scope['id']}:{edge['from']}",
                    "to": f"{scope['id']}:{edge['to']}",
                    "kind": "control",
                }
            )

    return {
        "protocolVersion": "multiverse/v0.1",
        "run": _run_summary(run),
        "scopes": [_scope_summary(scope) for scope in scopes],
        "nodes": nodes,
        "edges": edges,
        "events": [_event_summary(event) for event in ledger.list_events(run_id)],
        "humanRequests": [
            _human_request_summary(request)
            for request in ledger.list_human_requests(run_id=run_id)
        ],
        "artifacts": [
            _artifact_summary(artifact) for artifact in ledger.list_artifacts(run_id)
        ],
    }


def _scope_plan(plan: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    workflows = plan.get("workflows")
    if isinstance(workflows, dict):
        workflow = workflows.get(workflow_id)
        if isinstance(workflow, dict):
            return workflow
    if plan.get("workflowId") == workflow_id:
        return plan
    raise KeyError(f"frozen plan is missing workflow: {workflow_id}")


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        key: run[key]
        for key in (
            "id",
            "workflow_id",
            "package_digest",
            "binding_digest",
            "status",
            "control_mode",
            "current_node_id",
            "version",
            "deadline_at",
            "created_at",
            "updated_at",
            "rerun_of",
            "rerun_reason",
        )
    }


def _scope_summary(scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": scope["id"],
        "workflowId": scope["workflow_id"],
        "parentScopeId": scope["parent_scope_id"],
        "parentInvocationId": scope["parent_invocation_id"],
        "path": json.loads(scope["path_json"]),
        "inputDigest": scope["input_digest"],
        "status": scope["status"],
    }


def _invocation_summary(invocation: dict[str, Any] | None) -> dict[str, Any] | None:
    if invocation is None:
        return None
    return {
        "id": invocation["id"],
        "status": invocation["status"],
        "inputDigest": invocation["input_digest"],
        "version": invocation["version"],
        "createdAt": invocation["created_at"],
        "updatedAt": invocation["updated_at"],
        "hasOutput": invocation["output_json"] is not None,
        "error": _error_code(invocation["error_json"]),
    }


def _latest_attempt_summary(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not attempts:
        return None
    attempt = attempts[-1]
    return {
        "id": attempt["id"],
        "attemptNo": attempt["attempt_no"],
        "status": attempt["status"],
        "inputDigest": attempt["input_digest"],
        "externalRef": attempt["external_ref"],
        "createdAt": attempt["created_at"],
        "updatedAt": attempt["updated_at"],
        "hasOutput": attempt["output_json"] is not None,
        "error": _error_code(attempt["error_json"]),
    }


def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": event["seq"],
        "type": event["type"],
        "occurredAt": event["occurred_at"],
        "scopeId": event["scope_id"],
        "invocationId": event["invocation_id"],
        "attemptId": event["attempt_id"],
        "payload": json.loads(event["payload_json"]),
    }


def _human_request_summary(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": request["id"],
        "scopeId": request["scope_id"],
        "invocationId": request["invocation_id"],
        "requestType": request["request_type"],
        "title": request["title"],
        "subjectDigest": request["subject_digest"],
        "choices": json.loads(request["choices_json"]),
        "expiresAt": request["expires_at"],
        "version": request["version"],
        "status": request["status"],
    }


def _artifact_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": artifact["id"],
        "invocationId": artifact["invocation_id"],
        "name": artifact["name"],
        "mediaType": artifact["media_type"],
        "sizeBytes": artifact["size_bytes"],
        "digest": artifact["digest"],
        "status": artifact["status"],
        "createdAt": artifact["created_at"],
    }


def _node_type(definition: dict[str, Any], invocation: dict[str, Any] | None) -> str:
    if definition["type"] == "call" and invocation is not None:
        return "human" if invocation["status"] == "waiting" else "call"
    node_type = definition["type"]
    return node_type if isinstance(node_type, str) else "unknown"


def _node_status(scope: dict[str, Any], invocation: dict[str, Any] | None) -> str:
    if invocation is None:
        return "cancelled" if scope["status"] == "cancelled" else "pending"
    status = invocation["status"]
    return "failed" if status == "cancelled" else status


def _error_code(error_json: str | None) -> str | None:
    if error_json is None:
        return None
    error = json.loads(error_json)
    return error.get("code") if isinstance(error, dict) else None
