import pytest
from pydantic import ValidationError

from multiverse_workflow.service.contracts import (
    AttemptReconcileRequest,
    CodexInteractionResponseRequest,
    CommandReceipt,
    RunCreateRequest,
)


def test_run_create_request_requires_deployment_fields() -> None:
    with pytest.raises(ValidationError):
        RunCreateRequest.model_validate({"input": {"goal": "ship"}})


def test_command_receipt_is_accepted_until_runtime_processes_it() -> None:
    receipt = CommandReceipt(
        request_id="request_1",
        status="accepted",
        resource_id="run_1",
        operation="run.create",
    )

    assert receipt.model_dump()["status"] == "accepted"


def test_attempt_reconcile_request_requires_evidence_and_supported_conclusion() -> None:
    request = AttemptReconcileRequest(
        expectedVersion=3,
        conclusion="confirmed_failed",
        evidenceRefs=["evidence://operator/123"],
        reason="The external execution returned a terminal failure.",
    )

    assert request.conclusion == "confirmed_failed"
    assert request.evidence_refs == ["evidence://operator/123"]

    with pytest.raises(ValidationError):
        AttemptReconcileRequest(
            expectedVersion=3,
            conclusion="unknown",
            evidenceRefs=[],
            reason="Cannot determine the result.",
        )

    with pytest.raises(ValidationError):
        AttemptReconcileRequest(
            expectedVersion=3,
            conclusion="confirmed_failed",
            evidenceRefs=["evidence://operator/123"],
            reason="The provider confirmed failure.",
            output={"unexpected": True},
        )


def test_codex_interaction_response_requires_a_version_and_object_payload() -> None:
    request = CodexInteractionResponseRequest(
        expectedVersion=1,
        response={"decision": "accept"},
    )
    assert request.expected_version == 1

    with pytest.raises(ValidationError):
        CodexInteractionResponseRequest(expectedVersion=0, response={})

    with pytest.raises(ValidationError):
        CodexInteractionResponseRequest(expectedVersion=1, response="accept")
