from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ServiceModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=None,
        extra="forbid",
        populate_by_name=True,
        strict=True,
    )


def _non_empty(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be empty")
    return value


class RunCreateRequest(ServiceModel):
    deployment_id: str = Field(alias="deploymentId", min_length=1)
    workflow_id: str = Field(alias="workflowId", min_length=1)
    input: Any
    external_refs: dict[str, str] = Field(default_factory=dict, alias="externalRefs")

    _validate_ids = field_validator("deployment_id", "workflow_id")(_non_empty)


class RunControlRequest(ServiceModel):
    expected_version: int = Field(alias="expectedVersion", ge=1)
    reason: str = Field(min_length=1)

    _validate_reason = field_validator("reason")(_non_empty)


class HumanDecisionRequest(ServiceModel):
    expected_version: int = Field(alias="expectedVersion", ge=1)
    subject_digest: str = Field(alias="subjectDigest", min_length=1)
    choice: str | None = Field(default=None, min_length=1)
    decision: Any | None = None
    comment: str = ""

    _validate_text = field_validator("subject_digest")(_non_empty)


ReconcileConclusion = Literal[
    "confirmed_succeeded",
    "confirmed_failed",
    "confirmed_cancelled",
    "confirmed_not_started",
]


class AttemptReconcileRequest(ServiceModel):
    expected_version: int = Field(alias="expectedVersion", ge=1)
    conclusion: ReconcileConclusion
    evidence_refs: list[str] = Field(alias="evidenceRefs", min_length=1)
    output: Any | None = None
    reason: str = Field(min_length=1)

    _validate_reason = field_validator("reason")(_non_empty)

    @field_validator("evidence_refs")
    @classmethod
    def _validate_evidence_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("evidence references must not be empty")
        return values

    @model_validator(mode="after")
    def _validate_output_for_conclusion(self) -> AttemptReconcileRequest:
        if self.conclusion == "confirmed_succeeded" and self.output is None:
            raise ValueError("confirmed_succeeded requires output")
        if self.conclusion != "confirmed_succeeded" and self.output is not None:
            raise ValueError("output is only allowed for confirmed_succeeded")
        return self


class CommandReceipt(ServiceModel):
    request_id: str = Field(alias="requestId", min_length=1)
    status: Literal["accepted", "completed", "rejected"] = "accepted"
    resource_id: str = Field(alias="resourceId", min_length=1)
    operation: str = Field(min_length=1)
    resource_version: int | None = Field(default=None, alias="resourceVersion", ge=1)


class ErrorBody(ServiceModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    next_actions: list[str] = Field(default_factory=list, alias="nextActions")


class ErrorResponse(ServiceModel):
    error: ErrorBody
    request_id: str = Field(alias="requestId", min_length=1)


class RunSummary(ServiceModel):
    id: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    workflow_id: str = Field(alias="workflowId", min_length=1)
    status: str = Field(min_length=1)
    control_mode: str = Field(alias="controlMode", min_length=1)
    version: int = Field(ge=1)
    current_scope_id: str | None = Field(default=None, alias="currentScopeId")
    current_node_id: str | None = Field(default=None, alias="currentNodeId")
    current_invocation_id: str | None = Field(
        default=None,
        alias="currentInvocationId",
    )
    created_at: str = Field(alias="createdAt", min_length=1)
    updated_at: str = Field(alias="updatedAt", min_length=1)
