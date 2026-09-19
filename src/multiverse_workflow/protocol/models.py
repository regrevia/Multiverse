from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEMVER_PATTERN = (
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
NAME_PATTERN = r"^[a-z][a-z0-9.-]{0,63}$"
CAPABILITY_PATTERN = r"^[a-z][a-z0-9.-]*\.[a-z][a-z0-9.-]*@[1-9][0-9]*$"


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


class Metadata(ProtocolModel):
    name: str = Field(pattern=NAME_PATTERN, min_length=1, max_length=64)
    version: str = Field(pattern=SEMVER_PATTERN)
    description: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class ResourceBase(ProtocolModel):
    api_version: Literal["multiverse/v0.1"] = Field(alias="apiVersion")
    kind: str
    metadata: Metadata


class LiteralExpr(ProtocolModel):
    literal: Any


class RefExpr(ProtocolModel):
    ref: str = Field(min_length=1)


class ObjectExpr(ProtocolModel):
    object: dict[str, ValueExpr]


class ArrayExpr(ProtocolModel):
    array: list[ValueExpr]


type ValueExpr = Annotated[
    LiteralExpr | RefExpr | ObjectExpr | ArrayExpr,
    Field(union_mode="smart"),
]


class ComparisonPredicate(ProtocolModel):
    op: Literal["eq", "ne", "lt", "lte", "gt", "gte", "in"]
    left: ValueExpr
    right: ValueExpr


class AllPredicate(ProtocolModel):
    all: list[Predicate] = Field(min_length=1)


class AnyPredicate(ProtocolModel):
    any: list[Predicate] = Field(min_length=1)


class NotPredicate(ProtocolModel):
    not_: Predicate = Field(alias="not")


type Predicate = Annotated[
    ComparisonPredicate | AllPredicate | AnyPredicate | NotPredicate,
    Field(union_mode="smart"),
]


class Requires(ProtocolModel):
    capabilities: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_capabilities(self) -> Requires:
        for capability in self.capabilities:
            if not _matches(capability, CAPABILITY_PATTERN):
                raise ValueError(f"invalid capability ID: {capability}")
        return self


class Effects(ProtocolModel):
    effect_class: Literal["none", "read", "write"] = Field(alias="class")
    actions: list[str]


class RetryPolicy(ProtocolModel):
    max_attempts: int = Field(default=1, alias="maxAttempts", ge=1, le=3)
    initial_delay_seconds: int = Field(default=2, alias="initialDelaySeconds", ge=0)
    backoff_multiplier: int | float = Field(default=2, alias="backoffMultiplier", ge=1)
    max_delay_seconds: int = Field(default=30, alias="maxDelaySeconds", ge=0)
    retryable_codes: list[str] = Field(default_factory=list, alias="retryableCodes")


class NodeCommon(ProtocolModel):
    title: str | None = None
    description: str | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)
    deadline_seconds: int | None = Field(default=None, alias="deadlineSeconds", ge=1)
    on_error: str | None = Field(default=None, alias="onError", min_length=1)


class CallNode(NodeCommon):
    type: Literal["call"]
    slot: str = Field(min_length=1)
    input_schema: str = Field(alias="inputSchema", min_length=1)
    output_schema: str = Field(alias="outputSchema", min_length=1)
    input: ValueExpr
    requires: Requires
    effects: Effects
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    next: str = Field(min_length=1)


class SwitchCase(ProtocolModel):
    id: str = Field(pattern=NAME_PATTERN, min_length=1, max_length=64)
    when: Predicate
    next: str = Field(min_length=1)


class SwitchNode(NodeCommon):
    type: Literal["switch"]
    cases: list[SwitchCase] = Field(min_length=1)
    default: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> SwitchNode:
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("switch case IDs must be unique")
        return self

    @model_validator(mode="after")
    def reject_error_handler(self) -> SwitchNode:
        if self.on_error is not None:
            raise ValueError("switch nodes cannot define onError")
        return self


class WorkflowNode(NodeCommon):
    type: Literal["workflow"]
    workflow: str = Field(min_length=1)
    input: ValueExpr
    next: str = Field(min_length=1)


class ParallelBranch(ProtocolModel):
    workflow: str = Field(min_length=1)
    input: ValueExpr


class ParallelNode(NodeCommon):
    type: Literal["parallel"]
    branches: dict[str, ParallelBranch] = Field(min_length=2, max_length=16)
    join: Literal["all"]
    max_concurrency: int | None = Field(default=None, alias="maxConcurrency", ge=1, le=16)
    next: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_concurrency(self) -> ParallelNode:
        if self.max_concurrency is not None and self.max_concurrency > len(self.branches):
            raise ValueError("maxConcurrency cannot exceed branch count")
        return self


class RepeatNode(NodeCommon):
    type: Literal["repeat"]
    workflow: str = Field(min_length=1)
    input: ValueExpr
    until: Predicate
    feedback: ValueExpr
    max_iterations: int = Field(alias="maxIterations", ge=1, le=20)
    next: str = Field(min_length=1)


class EndError(ProtocolModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class EndNode(NodeCommon):
    type: Literal["end"]
    outcome: Literal["succeeded", "failed"]
    output: ValueExpr | None = None
    error: EndError | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> EndNode:
        if self.on_error is not None:
            raise ValueError("end nodes cannot define onError")
        if self.outcome == "succeeded" and (self.output is None or self.error is not None):
            raise ValueError("successful end requires output and cannot contain error")
        if self.outcome == "failed" and (self.error is None or self.output is not None):
            raise ValueError("failed end requires error and cannot contain output")
        return self


type Node = Annotated[
    CallNode | SwitchNode | WorkflowNode | ParallelNode | RepeatNode | EndNode,
    Field(discriminator="type"),
]


class WorkflowDefaults(ProtocolModel):
    run_deadline_seconds: int = Field(default=604800, alias="runDeadlineSeconds", ge=1)
    call_deadline_seconds: int = Field(default=3600, alias="callDeadlineSeconds", ge=1)
    max_attempts: int = Field(default=1, alias="maxAttempts", ge=1, le=3)
    max_concurrency: int = Field(default=4, alias="maxConcurrency", ge=1, le=16)


class WorkflowSpec(ProtocolModel):
    input_schema: str = Field(alias="inputSchema", min_length=1)
    output_schema: str = Field(alias="outputSchema", min_length=1)
    entry: str = Field(min_length=1)
    nodes: dict[str, Node] = Field(min_length=1, max_length=200)
    defaults: WorkflowDefaults = Field(default_factory=WorkflowDefaults)
    extensions: dict[str, Any] = Field(default_factory=dict)


class Workflow(ResourceBase):
    kind: Literal["Workflow"]
    spec: WorkflowSpec


class AssetSpec(ProtocolModel):
    path: str = Field(min_length=1)
    kind: Literal["prompt", "skill", "policy"]
    format: str = Field(min_length=1)
    version: str = Field(pattern=SEMVER_PATTERN)


class WorkflowPackageSpec(ProtocolModel):
    workflows: dict[str, str] = Field(min_length=1)
    entrypoints: list[str] = Field(min_length=1, alias="entrypoints")
    required_features: list[str] = Field(default_factory=list, alias="requiredFeatures")
    assets: dict[str, AssetSpec] = Field(default_factory=dict)
    eval_suites: list[str] = Field(default_factory=list, alias="evalSuites")
    extensions: dict[str, Any] = Field(default_factory=dict)


class WorkflowPackage(ResourceBase):
    kind: Literal["WorkflowPackage"]
    spec: WorkflowPackageSpec


class Grant(ProtocolModel):
    action: str = Field(min_length=1)
    resource: str = Field(min_length=1)


class SlotBinding(ProtocolModel):
    adapter: Literal["builtin", "local_process", "http_job", "human"]
    executor_ref: str = Field(alias="executorRef", min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict, alias="secretRefs")
    grants: list[Grant] = Field(default_factory=list)

    @field_validator("secret_refs")
    @classmethod
    def validate_secret_refs(cls, value: dict[str, str]) -> dict[str, str]:
        for key, reference in value.items():
            if not reference.startswith("secret://") or len(reference) <= len("secret://"):
                raise ValueError(f"secretRefs.{key} must use secret:// references")
        return value


class BindingSetSpec(ProtocolModel):
    slots: dict[str, SlotBinding] = Field(min_length=1)
    limits: dict[str, Any] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class BindingSet(ResourceBase):
    kind: Literal["BindingSet"]
    spec: BindingSetSpec


def _matches(value: str, pattern: str) -> bool:
    import re

    return re.fullmatch(pattern, value) is not None


for _model in (
    ObjectExpr,
    ArrayExpr,
    ComparisonPredicate,
    AllPredicate,
    AnyPredicate,
    NotPredicate,
):
    _model.model_rebuild()
