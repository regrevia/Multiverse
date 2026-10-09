from __future__ import annotations

import json
from collections import defaultdict
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

from multiverse_workflow.compiler.digests import binding_digest
from multiverse_workflow.protocol.models import BindingSet
from multiverse_workflow.runtime.ledger import Ledger


def build_run_projection(
    ledger: Ledger,
    run_id: str,
    *,
    binding: BindingSet | None = None,
) -> dict[str, Any]:
    """Build a read-only Inspector DTO from one persisted Run."""
    run = ledger.get_run(run_id)
    if run is None:
        raise KeyError(f"run not found: {run_id}")
    plan = json.loads(run["plan_json"])
    binding_is_current = _binding_matches_run(binding, run)
    binding_slots = binding.spec.slots if binding_is_current and binding is not None else {}
    scopes = ledger.list_scopes(run_id)
    invocations = ledger.list_invocations(run_id)
    attempts = ledger.list_attempts(run_id)
    waits = ledger.list_waits(
        run_id=run_id,
        statuses=("pending", "claimed"),
    )
    human_requests = ledger.list_human_requests(run_id=run_id)
    human_requests_by_invocation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for request in human_requests:
        human_requests_by_invocation[request["invocation_id"]].append(request)
    waits_by_invocation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for wait in waits:
        if wait["invocation_id"] is not None:
            waits_by_invocation[wait["invocation_id"]].append(wait)
    child_scopes_by_invocation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for child_scope in scopes:
        if child_scope["parent_invocation_id"] is not None:
            child_scopes_by_invocation[child_scope["parent_invocation_id"]].append(
                child_scope
            )
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
        node_definitions = {
            node_id: value["definition"]
            for node_id, value in scope_plan["nodes"].items()
        }
        data_sources, data_targets = _scope_data_dependencies(node_definitions)
        for node_id, definition in scope_plan["nodes"].items():
            invocation = invocations_by_scope_node.get((scope["id"], node_id))
            node_requests = (
                human_requests_by_invocation.get(invocation["id"], [])
                if invocation is not None
                else []
            )
            human_request = next(
                (request for request in node_requests if request["status"] == "pending"),
                None,
            )
            any_human_request = node_requests[0] if node_requests else None
            node_definition = definition["definition"]
            node_type = str(node_definition.get("type", "unknown"))
            child_scopes = (
                child_scopes_by_invocation.get(invocation["id"], [])
                if invocation is not None
                else []
            )
            active_child_scopes = [
                child_scope for child_scope in child_scopes
                if child_scope["status"] == "active"
            ]
            waiting_reason = _waiting_reason(
                invocation,
                human_request=human_request,
                waits=(
                    waits_by_invocation.get(invocation["id"], [])
                    if invocation is not None
                    else []
                ),
                child_scopes=child_scopes,
                node_type=node_type,
                invocation_id=invocation["id"] if invocation is not None else None,
            )
            node_status = _node_status(scope, invocation)
            if active_child_scopes and node_type in {"workflow", "repeat", "parallel"}:
                node_status = "waiting"
            slot = (
                binding_slots.get(str(node_definition.get("slot")))
                if node_type == "call"
                else None
            )
            nodes.append(
                {
                    "id": f"{scope['id']}:{node_id}",
                    "scopeId": scope["id"],
                    "nodeId": node_id,
                    "title": definition["definition"].get("title", node_id),
                    "type": _node_type(definition),
                    "status": node_status,
                    "execution": _execution_summary(
                        slot,
                        node_definition,
                        human_request=any_human_request,
                    ),
                    "waitingReason": waiting_reason,
                    "inputSummary": _node_input_summary(
                        invocation,
                        node_definition.get("inputSchema"),
                    ),
                    "outputSummary": _node_output_summary(
                        invocation,
                        node_definition.get("outputSchema"),
                    ),
                    "dataSources": data_sources[node_id],
                    "dataTargets": data_targets[node_id],
                    "invocation": _invocation_summary(invocation),
                    "latestAttempt": _latest_attempt_summary(
                        attempts_by_invocation.get(invocation["id"], [])
                        if invocation is not None
                        else []
                    ),
                    "attempts": _attempt_summaries(
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
            for request in human_requests
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


def _scope_data_dependencies(
    definitions: dict[str, dict[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    titles = {
        node_id: str(definition.get("title") or node_id)
        for node_id, definition in definitions.items()
    }
    sources: dict[str, list[str]] = {}
    targets: dict[str, list[str]] = {node_id: [] for node_id in definitions}
    for node_id, definition in definitions.items():
        node_type = definition.get("type")
        expressions: list[Any] = []
        if node_type in {"call", "workflow", "repeat"}:
            expressions.append(definition.get("input"))
        if node_type == "repeat":
            expressions.extend((definition.get("feedback"), definition.get("until")))
        elif node_type == "switch":
            expressions.append(definition.get("cases"))
        elif node_type == "parallel":
            expressions.append(definition.get("branches"))
        elif node_type == "end":
            expressions.append(definition.get("output"))
        references = list(
            dict.fromkeys(
                reference
                for expression in expressions
                for reference in _expression_refs(expression)
            )
        )
        source_ids: list[str] = []
        labels: list[str] = []
        for reference in references:
            source_id = _reference_source_node(reference)
            if source_id is None:
                if reference.startswith("input#") and "工作流输入" not in labels:
                    labels.append("工作流输入")
                continue
            if source_id not in definitions or source_id in source_ids:
                continue
            source_ids.append(source_id)
            labels.append(titles[source_id])
            targets[source_id].append(titles[node_id])
        sources[node_id] = labels
    return (
        sources,
        {
            node_id: list(dict.fromkeys(node_titles))
            for node_id, node_titles in targets.items()
        },
    )


def _expression_refs(value: Any) -> list[str]:
    references: list[str] = []
    if isinstance(value, dict):
        reference = value.get("ref")
        if isinstance(reference, str):
            references.append(reference)
        for key, child in value.items():
            if key != "ref":
                references.extend(_expression_refs(child))
    elif isinstance(value, list):
        for child in value:
            references.extend(_expression_refs(child))
    return list(dict.fromkeys(references))


def _reference_source_node(reference: str) -> str | None:
    if not reference.startswith("nodes."):
        return None
    path = reference.split("#", 1)[0].split(".")
    if len(path) != 3 or path[0] != "nodes" or path[2] != "output":
        return None
    return path[1]


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        key: run[key]
        for key in (
        "id",
        "deployment_id",
        "workflow_id",
            "package_digest",
            "binding_digest",
            "status",
            "control_mode",
            "current_scope_id",
            "current_node_id",
            "current_invocation_id",
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
        "version": attempt["version"],
        "inputDigest": attempt["input_digest"],
        "externalRef": attempt["external_ref"],
        "createdAt": attempt["created_at"],
        "updatedAt": attempt["updated_at"],
        "hasOutput": attempt["output_json"] is not None,
        "error": _error_code(attempt["error_json"]),
        "reconciliation": _reconciliation_summary(attempt["reconciliation_json"]),
    }


def _attempt_summaries(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_attempt_summary(attempt) for attempt in attempts]


def _attempt_summary(attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": attempt["id"],
        "attemptNo": attempt["attempt_no"],
        "status": attempt["status"],
        "version": attempt["version"],
        "externalRef": attempt["external_ref"],
        "createdAt": attempt["created_at"],
        "updatedAt": attempt["updated_at"],
        "reconciliation": _reconciliation_summary(attempt["reconciliation_json"]),
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


def _node_type(definition: dict[str, Any]) -> str:
    node_type = definition["type"]
    return node_type if isinstance(node_type, str) else "unknown"


def _binding_matches_run(binding: BindingSet | None, run: dict[str, Any]) -> bool:
    if binding is None or run.get("binding_digest") is None:
        return False
    binding_value = binding.model_dump(mode="json", by_alias=True, exclude_none=True)
    return bool(binding_digest(binding_value) == run["binding_digest"])


def _execution_summary(
    slot: Any,
    node_definition: dict[str, Any],
    *,
    human_request: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if node_definition.get("type") != "call":
        return None
    if human_request is not None:
        return {
            "participantType": "human",
            "adapter": getattr(slot, "adapter", "human"),
            "executorRef": getattr(slot, "executor_ref", None),
            "location": "human",
            "target": "Runtime 人工任务",
            "model": None,
            "workspace": None,
        }
    if slot is None:
        return {
            "participantType": "unknown",
            "adapter": None,
            "executorRef": None,
            "location": "unknown",
            "target": "Binding 未核实",
            "model": None,
            "workspace": None,
        }

    adapter = slot.adapter
    executor_ref = slot.executor_ref
    config = slot.config
    if adapter == "human":
        participant = "human"
        location = "human"
        target = "Runtime 人工入口"
    elif adapter in {"codex", "claude", "pi"}:
        participant = "agent"
        location = "local"
        target = "本机 CLI"
    elif adapter == "http_job":
        participant = "unknown"
        location = "external"
        target = _http_target(config.get("baseUrl"))
    elif adapter == "local_process":
        participant = "unknown"
        location = "local"
        target = "本机进程入口"
    elif executor_ref == "builtin.ollama-deliverable.v1":
        participant = "agent"
        location = "local"
        target = "本机模型服务"
    else:
        participant = "program"
        location = "runtime"
        target = "Multiverse Runtime"

    return {
        "participantType": participant,
        "adapter": adapter,
        "executorRef": executor_ref,
        "location": location,
        "target": target,
        "model": _safe_config_label(config.get("model")),
        "workspace": _safe_path_label(
            config.get("workspaceRoot") or config.get("cwd")
        ),
    }


def _http_target(value: Any) -> str:
    if not isinstance(value, str):
        return "外部 HTTP 服务"
    try:
        host = urlsplit(value).hostname
    except ValueError:
        host = None
    return f"外部服务 · {host}" if host else "外部 HTTP 服务"


def _safe_config_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized[:80] or None


def _safe_path_label(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.replace("\\", "/").rstrip("/")
    return PureWindowsPath(value).name or PurePosixPath(normalized).name or None


def _waiting_reason(
    invocation: dict[str, Any] | None,
    *,
    human_request: dict[str, Any] | None,
    waits: list[dict[str, Any]],
    child_scopes: list[dict[str, Any]],
    node_type: str,
    invocation_id: str | None = None,
) -> str | None:
    status = invocation["status"] if invocation is not None else "pending"
    if human_request is not None:
        return "等待人工处理"
    wait_kinds = {wait["kind"] for wait in waits}
    if "external-observe" in wait_kinds:
        return "等待外部服务"
    if "external-submit" in wait_kinds:
        return "等待提交确认"
    if "retry" in wait_kinds or status == "retry_wait":
        return "等待重试时间"
    if "human-progress" in wait_kinds:
        return "等待 Runtime 恢复人工决定"
    if invocation_id is not None and node_type in {"workflow", "repeat", "parallel"}:
        active_children = [
            child_scope
            for child_scope in child_scopes
            if child_scope["status"] == "active"
        ]
        if active_children:
            return _child_scope_wait_reason(
                node_type,
                child_scopes,
                active_children,
            )
    if status == "waiting":
        return None
    if status in {"planned", "ready", "pending"}:
        return "等待上游节点"
    if status in {"unknown", "reconciling"}:
        return "执行结果待核对"
    if status == "blocked":
        return "需要人工核对"
    return None


def _child_scope_wait_reason(
    node_type: str,
    child_scopes: list[dict[str, Any]],
    active_children: list[dict[str, Any]],
) -> str:
    if node_type == "repeat":
        latest = active_children[-1]
        path = json.loads(latest["path_json"])
        iteration = path[-1] if path and str(path[-1]).isdigit() else len(child_scopes)
        return f"等待第 {iteration} 轮子流程完成"
    if node_type == "parallel":
        return f"等待并行分支汇合 · {len(active_children)} 个分支进行中"
    return "等待子流程完成"


def _node_input_summary(
    invocation: dict[str, Any] | None,
    schema_ref: Any,
) -> str:
    if invocation is not None:
        return _json_shape_summary(invocation["input_json"], "未提供输入")
    return _schema_label(schema_ref, "待输入")


def _node_output_summary(
    invocation: dict[str, Any] | None,
    schema_ref: Any,
) -> str:
    if invocation is None:
        return _schema_label(schema_ref, "尚无输出")
    return _json_shape_summary(invocation["output_json"], "尚无输出")


def _json_shape_summary(value_json: str | None, empty: str) -> str:
    if value_json is None:
        return empty
    try:
        value = json.loads(value_json)
    except (TypeError, ValueError):
        return "输出已记录"
    if isinstance(value, dict):
        keys = [str(key) for key in value]
        if not keys:
            return "空对象"
        labels = keys[:2]
        if len(keys) > 2:
            labels.append(f"+{len(keys) - 2}")
        return " · ".join(labels)
    if isinstance(value, list):
        return f"{len(value)} 项"
    if isinstance(value, str):
        return "文本"
    if isinstance(value, bool):
        return "布尔值"
    if isinstance(value, (int, float)):
        return "数值"
    if value is None:
        return empty
    return "已记录"


def _schema_label(value: Any, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    return PurePosixPath(value.replace("\\", "/")).name


def _node_status(scope: dict[str, Any], invocation: dict[str, Any] | None) -> str:
    if invocation is None:
        return "cancelled" if scope["status"] == "cancelled" else "pending"
    return str(invocation["status"])


def _error_code(error_json: str | None) -> str | None:
    if error_json is None:
        return None
    error = json.loads(error_json)
    return error.get("code") if isinstance(error, dict) else None


def _reconciliation_summary(reconciliation_json: str | None) -> dict[str, Any] | None:
    if reconciliation_json is None:
        return None
    reconciliation = json.loads(reconciliation_json)
    if not isinstance(reconciliation, dict):
        return None
    return {
        "conclusion": reconciliation.get("conclusion"),
        "evidenceRefs": reconciliation.get("evidenceRefs", []),
        "reason": reconciliation.get("reason"),
        "actor": reconciliation.get("actor"),
    }
