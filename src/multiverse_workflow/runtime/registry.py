from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from jsonschema import Draft202012Validator

from multiverse_workflow.protocol.models import BindingSet
from multiverse_workflow.runtime.config_schemas import executor_config_schema

AdapterKind = Literal["builtin", "local_process", "http_job", "human"]


@dataclass(frozen=True)
class ExecutorDescriptor:
    executor_ref: str
    adapter: AdapterKind
    capabilities: frozenset[str]
    contract_version: str
    executor_version: str
    supports_cancel: bool
    supports_idempotency: bool
    supports_recovery_query: bool
    observability_level: str
    permission_level: str
    installed: bool
    available: bool
    verified: bool

    config_schema_json: str | None = None
    config_schema_ref: str | None = None
    config_schema_digest: str | None = None
    verification_evidence_json: str | None = None

    def config_schema(self) -> dict[str, Any]:
        base = executor_config_schema(self.adapter, self.executor_ref)
        if self.config_schema_json is None:
            return base
        return {"allOf": [base, json.loads(self.config_schema_json)]}

    def as_catalog_entry(self) -> dict[str, object]:
        return {
            "executorRef": self.executor_ref,
            "adapter": self.adapter,
            "capabilities": sorted(self.capabilities),
            "contractVersion": self.contract_version,
            "executorVersion": self.executor_version,
            "supportsCancel": self.supports_cancel,
            "supportsIdempotency": self.supports_idempotency,
            "supportsRecoveryQuery": self.supports_recovery_query,
            "observabilityLevel": self.observability_level,
            "permissionLevel": self.permission_level,
            "declared": True,
            "installed": self.installed,
            "available": self.available,
            "verified": self.verified,
            "configSchema": self.config_schema(),
            "configSchemaRef": self.config_schema_ref,
            "effectiveConfigSchemaDigest": "sha256:"
            + hashlib.sha256(
                json.dumps(self.config_schema(), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "configSchemaDigest": self.config_schema_digest
            or (
                "sha256:"
                + hashlib.sha256(
                    json.dumps(self.config_schema(), sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
            ),
            "verificationEvidence": (
                json.loads(self.verification_evidence_json)
                if self.verification_evidence_json
                else None
            ),
        }


@dataclass(frozen=True)
class SupportIssue:
    code: str
    node_id: str
    message: str
    config_pointer: str | None = None
    expected: str | None = None
    actual: str | None = None


@dataclass(frozen=True)
class RegistryPreflightResult:
    issues: list[SupportIssue]
    config_checked: bool


class ExecutorRegistry:
    def __init__(
        self,
        descriptors: Iterable[ExecutorDescriptor],
        *,
        snapshot_validator: Callable[[], None] | None = None,
    ) -> None:
        items = tuple(descriptors)
        indexed = {descriptor.executor_ref: descriptor for descriptor in items}
        if len(indexed) != len(items):
            raise ValueError("executor references must be unique")
        self._descriptors = indexed
        self._snapshot_validator = snapshot_validator

    def resolve(self, executor_ref: str) -> ExecutorDescriptor | None:
        return self._descriptors.get(executor_ref)

    def snapshot(self) -> ExecutorRegistry:
        return ExecutorRegistry(
            self._descriptors.values(), snapshot_validator=self._snapshot_validator
        )

    def descriptors(self) -> tuple[ExecutorDescriptor, ...]:
        return tuple(self._descriptors.values())

    def capability_catalog(self) -> list[dict[str, object]]:
        return [
            descriptor.as_catalog_entry() for _, descriptor in sorted(self._descriptors.items())
        ]

    def preflight(
        self,
        *,
        nodes: dict[str, dict[str, Any]],
        binding: BindingSet,
    ) -> list[SupportIssue]:
        return self.preflight_result(nodes=nodes, binding=binding).issues

    def preflight_result(
        self,
        *,
        nodes: dict[str, dict[str, Any]],
        binding: BindingSet,
    ) -> RegistryPreflightResult:
        config_checked = True
        issues: list[SupportIssue] = []
        if self._snapshot_validator is not None:
            try:
                self._snapshot_validator()
            except ValueError:
                return RegistryPreflightResult(
                    [
                        SupportIssue(
                            code="EXECUTOR_CATALOG_REVOKED",
                            node_id=node_id,
                            message="注册目录已更改或撤销；请显式重新加载。",
                        )
                        for node_id, node in nodes.items()
                        if node["type"] == "call"
                    ],
                    config_checked=False,
                )
        for node_id, node in nodes.items():
            if node["type"] != "call":
                continue
            definition = node["definition"]
            slot_name = definition["slot"]
            slot = binding.spec.slots.get(slot_name)
            if slot is None:
                config_checked = False
                issues.append(
                    SupportIssue(
                        code="BINDING_UNRESOLVED",
                        node_id=node_id,
                        message=f"逻辑 slot 未绑定：{slot_name}。",
                    )
                )
                continue
            descriptor = self.resolve(slot.executor_ref)
            if descriptor is None:
                config_checked = False
                issues.append(
                    SupportIssue(
                        code="EXECUTOR_UNRESOLVED",
                        node_id=node_id,
                        message=f"执行器未注册：{slot.executor_ref}。",
                    )
                )
                continue
            seen: set[tuple[str, str]] = set()
            for error in Draft202012Validator(descriptor.config_schema()).iter_errors(slot.config):
                path = list(error.absolute_path)
                paths = [path]
                if error.validator == "required":
                    paths = [
                        path + [key] for key in error.validator_value if key not in error.instance
                    ]
                elif error.validator == "additionalProperties" and isinstance(error.instance, dict):
                    allowed = error.schema.get("properties", {})
                    patterns = error.schema.get("patternProperties", {})
                    paths = [
                        path + [key]
                        for key in error.instance
                        if key not in allowed and not any(re.search(p, key) for p in patterns)
                    ]
                for precise_path in paths:
                    pointer = "".join(
                        "/" + str(key).replace("~", "~0").replace("/", "~1") for key in precise_path
                    )
                    constraint = str(error.validator)
                    if (pointer, constraint) in seen:
                        continue
                    seen.add((pointer, constraint))
                    expected = f"schema constraint: {constraint}"
                    if constraint in {
                        "minimum",
                        "maximum",
                        "exclusiveMinimum",
                        "exclusiveMaximum",
                        "minItems",
                        "maxItems",
                        "minLength",
                        "maxLength",
                        "type",
                    }:
                        expected += f" {error.validator_value}"
                    issues.append(
                        SupportIssue(
                            code="EXECUTOR_CONFIG_INVALID",
                            node_id=node_id,
                            message="执行器配置不符合已注册 Schema；配置值已隐藏。",
                            config_pointer=pointer,
                            expected=expected,
                            actual=(
                                "missing"
                                if constraint == "required"
                                else f"{type(error.instance).__name__} (value redacted)"
                            ),
                        )
                    )
            if slot.adapter != descriptor.adapter:
                issues.append(
                    SupportIssue(
                        code="EXECUTOR_ADAPTER_MISMATCH",
                        node_id=node_id,
                        message=(
                            f"执行器 {slot.executor_ref} 要求 adapter "
                            f"{descriptor.adapter}，实际为 {slot.adapter}。"
                        ),
                    )
                )
            for capability in definition["requires"]["capabilities"]:
                if capability not in descriptor.capabilities:
                    issues.append(
                        SupportIssue(
                            code="CAPABILITY_MISMATCH",
                            node_id=node_id,
                            message=f"执行器 {slot.executor_ref} 不声明能力 {capability}。",
                        )
                    )
            if not descriptor.installed:
                issues.append(
                    SupportIssue(
                        code="EXECUTOR_NOT_INSTALLED",
                        node_id=node_id,
                        message=f"执行器未安装：{slot.executor_ref}。",
                    )
                )
            if not descriptor.available:
                issues.append(
                    SupportIssue(
                        code="EXECUTOR_UNAVAILABLE",
                        node_id=node_id,
                        message=f"执行器当前不可用：{slot.executor_ref}。",
                    )
                )
            if not descriptor.verified:
                issues.append(
                    SupportIssue(
                        code="EXECUTOR_UNVERIFIED",
                        node_id=node_id,
                        message=f"执行器尚未通过本地验证：{slot.executor_ref}。",
                    )
                )
        return RegistryPreflightResult(issues, config_checked=config_checked)


_LOCAL_EXECUTOR_DESCRIPTORS = (
    ExecutorDescriptor(
        executor_ref="local.process.v1",
        adapter="local_process",
        capabilities=frozenset({"data.process@1"}),
        contract_version="multiverse/v0.1",
        executor_version="1.0.0",
        supports_cancel=False,
        supports_idempotency=False,
        supports_recovery_query=False,
        observability_level="structured",
        permission_level="trusted_local",
        installed=True,
        available=True,
        verified=True,
    ),
    ExecutorDescriptor(
        executor_ref="example.content-fixture.v1",
        adapter="builtin",
        capabilities=frozenset({"content.produce@1", "content.review@1"}),
        contract_version="multiverse/v0.1",
        executor_version="1.0.0",
        supports_cancel=True,
        supports_idempotency=True,
        supports_recovery_query=True,
        observability_level="structured",
        permission_level="enforced",
        installed=True,
        available=True,
        verified=True,
    ),
    ExecutorDescriptor(
        executor_ref="example.remote-content.v1",
        adapter="http_job",
        capabilities=frozenset({"content.produce@1", "content.review@1"}),
        contract_version="multiverse/v0.1",
        executor_version="1.0.0",
        supports_cancel=True,
        supports_idempotency=True,
        supports_recovery_query=True,
        observability_level="external",
        permission_level="enforced",
        installed=False,
        available=False,
        verified=False,
    ),
    ExecutorDescriptor(
        executor_ref="builtin.nonempty-deliverable.v1",
        adapter="builtin",
        capabilities=frozenset({"data.validate@1"}),
        contract_version="multiverse/v0.1",
        executor_version="1.0.0",
        supports_cancel=True,
        supports_idempotency=True,
        supports_recovery_query=True,
        observability_level="structured",
        permission_level="enforced",
        installed=True,
        available=True,
        verified=True,
    ),
    ExecutorDescriptor(
        executor_ref="builtin.ollama-deliverable.v1",
        adapter="builtin",
        capabilities=frozenset({"content.produce@1", "content.review@1"}),
        contract_version="multiverse/v0.1",
        executor_version="1.0.0",
        supports_cancel=False,
        supports_idempotency=False,
        supports_recovery_query=False,
        observability_level="structured",
        permission_level="enforced",
        installed=True,
        available=True,
        verified=True,
    ),
    ExecutorDescriptor(
        executor_ref="builtin.human-review.v1",
        adapter="human",
        capabilities=frozenset({"human.review@1"}),
        contract_version="multiverse/v0.1",
        executor_version="1.0.0",
        supports_cancel=True,
        supports_idempotency=True,
        supports_recovery_query=True,
        observability_level="structured",
        permission_level="enforced",
        installed=True,
        available=True,
        verified=True,
    ),
    ExecutorDescriptor(
        executor_ref="builtin.human-input.v1",
        adapter="human",
        capabilities=frozenset({"human.input@1"}),
        contract_version="multiverse/v0.1",
        executor_version="1.0.0",
        supports_cancel=True,
        supports_idempotency=True,
        supports_recovery_query=True,
        observability_level="structured",
        permission_level="enforced",
        installed=True,
        available=True,
        verified=True,
    ),
)


def local_executor_registry() -> ExecutorRegistry:
    return ExecutorRegistry(_LOCAL_EXECUTOR_DESCRIPTORS)
