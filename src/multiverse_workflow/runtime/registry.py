from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from multiverse_workflow.protocol.models import BindingSet

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
        }


@dataclass(frozen=True)
class SupportIssue:
    code: str
    node_id: str
    message: str


class ExecutorRegistry:
    def __init__(self, descriptors: Iterable[ExecutorDescriptor]) -> None:
        items = tuple(descriptors)
        indexed = {descriptor.executor_ref: descriptor for descriptor in items}
        if len(indexed) != len(items):
            raise ValueError("executor references must be unique")
        self._descriptors = indexed

    def resolve(self, executor_ref: str) -> ExecutorDescriptor | None:
        return self._descriptors.get(executor_ref)

    def snapshot(self) -> ExecutorRegistry:
        return ExecutorRegistry(self._descriptors.values())

    def capability_catalog(self) -> list[dict[str, object]]:
        return [
            descriptor.as_catalog_entry()
            for _, descriptor in sorted(self._descriptors.items())
        ]

    def preflight(
        self,
        *,
        nodes: dict[str, dict[str, Any]],
        binding: BindingSet,
    ) -> list[SupportIssue]:
        issues: list[SupportIssue] = []
        for node_id, node in nodes.items():
            if node["type"] != "call":
                continue
            definition = node["definition"]
            slot_name = definition["slot"]
            slot = binding.spec.slots.get(slot_name)
            if slot is None:
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
                issues.append(
                    SupportIssue(
                        code="EXECUTOR_UNRESOLVED",
                        node_id=node_id,
                        message=f"执行器未注册：{slot.executor_ref}。",
                    )
                )
                continue
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
        return issues


_LOCAL_EXECUTOR_DESCRIPTORS = (
    ExecutorDescriptor(
        executor_ref="example.content-fixture.v1",
        adapter="builtin",
        capabilities=frozenset({"content.produce@1"}),
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
        capabilities=frozenset({"content.produce@1"}),
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
