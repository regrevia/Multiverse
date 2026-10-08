from __future__ import annotations

import inspect
from typing import Any

from multiverse_workflow.runtime.ledger import Ledger


class LedgerBackendError(RuntimeError):
    """A configured runtime ledger does not implement the Runner contract."""


LEDGER_BACKEND_METHODS: tuple[str, ...] = (
    "close",
    "create_run",
    "create_queued_run",
    "create_scope",
    "create_invocation",
    "create_attempt",
    "get_run",
    "update_run",
    "control_run",
    "get_scope",
    "get_invocation",
    "get_invocation_for_node",
    "get_attempt",
    "latest_attempt",
    "finish_scope",
    "finish_invocation",
    "finish_attempt",
    "list_scopes",
    "list_invocations",
    "list_attempts",
    "list_waits",
    "list_due_waits",
    "claim_wait",
    "complete_wait",
    "release_wait",
    "get_wait_by_key",
    "get_wait",
    "list_queued_runs",
    "record_event",
    "get_human_request",
    "list_human_requests",
    "decide_human_request",
    "claim_submit_outbox",
    "complete_human_progress_intent",
    "confirm_codex_interaction_delivery",
    "create_codex_interaction",
    "create_human_request",
    "ensure_attempt_reconciliation_wait",
    "ensure_external_observation_wait",
    "ensure_human_progress_intent",
    "ensure_submit_outbox",
    "expire_codex_interactions",
    "get_artifact",
    "get_codex_interaction",
    "get_codex_interaction_for_native_request",
    "get_human_decision",
    "get_human_decision_by_idempotency_key",
    "get_human_progress_intent",
    "get_outbox",
    "invalidate_codex_interaction",
    "invalidate_codex_interactions_for_attempt",
    "list_child_scopes",
    "list_scope_invocations",
    "list_codex_interactions",
    "mark_submit_outbox_retryable",
    "mark_submit_outbox_submitted",
    "mark_submit_outbox_unknown",
    "reconcile_attempt",
    "record_external_observation",
    "register_artifact_content",
    "register_external_artifacts",
    "resolve_unknown_submit",
    "schedule_retry",
    "validate_artifact_refs",
    "complete_wait_owned",
    "release_wait_owned",
    "reschedule_wait_owned",
    "requeue_stale_waits",
)


def missing_ledger_backend_methods(ledger: Any) -> list[str]:
    return [
        name
        for name in LEDGER_BACKEND_METHODS
        if not callable(getattr(ledger, name, None))
    ]


def validate_ledger_backend(ledger: Any) -> None:
    try:
        missing = missing_ledger_backend_methods(ledger)
    except Exception as exc:
        raise LedgerBackendError(
            "could not inspect ledger backend methods"
        ) from exc
    if missing:
        raise LedgerBackendError(
            "ledger backend is incompatible; missing methods: " + ", ".join(missing)
        )
    for name in LEDGER_BACKEND_METHODS:
        try:
            expected = inspect.signature(getattr(Ledger, name))
            actual = inspect.signature(getattr(ledger, name))
        except Exception as exc:
            raise LedgerBackendError(
                f"could not inspect ledger backend method: {name}"
            ) from exc
        expected_parameters = [
            parameter
            for parameter in expected.parameters.values()
            if parameter.name != "self"
        ]
        if any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in actual.parameters.values()
        ):
            raise LedgerBackendError(
                f"ledger backend method {name} cannot hide its contract behind kwargs"
            )
        positional_arguments: list[object] = []
        keyword_arguments: dict[str, object] = {}
        for parameter in expected_parameters:
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }:
                positional_arguments.append(object())
            elif parameter.kind == inspect.Parameter.KEYWORD_ONLY:
                keyword_arguments[parameter.name] = object()
        try:
            actual.bind(*positional_arguments, **keyword_arguments)
        except TypeError as exc:
            raise LedgerBackendError(
                f"ledger backend method {name} cannot accept Ledger calls"
            ) from exc
