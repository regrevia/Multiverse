"""Read-only local registry checks for workflow authors; never executes a node."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from multiverse_workflow.compiler.compiler import compile_package
from multiverse_workflow.compiler.digests import binding_digest
from multiverse_workflow.protocol.diagnostics import Diagnostic, DiagnosticError
from multiverse_workflow.protocol.loader import load_document
from multiverse_workflow.protocol.models import BindingSet
from multiverse_workflow.runtime.registry import ExecutorRegistry, local_executor_registry

_SUGGESTIONS = {
    "EXECUTOR_CONFIG_INVALID": "查询 capabilities --executor 的 configSchema，修正对应字段。",
    "EXECUTOR_NOT_INSTALLED": "安装已审核的执行器，或选择已经安装的兼容 Binding。",
    "EXECUTOR_UNAVAILABLE": "检查执行端可用性并更新注册记录，然后重新预检。",
    "EXECUTOR_UNVERIFIED": "完成执行器契约验证；不要通过删除验证要求绕过检查。",
}


@dataclass(frozen=True)
class PreflightReport:
    diagnostics: tuple[Diagnostic, ...]
    plan_digests: dict[str, str]
    registry_checked: bool = False
    config_checked: bool = False

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    def as_dict(self) -> dict[str, Any]:
        return {
            "reportVersion": "multiverse.preflight/v0.1",
            "scope": "local-registry",
            "ok": self.ok,
            "checked": [
                "static-validation",
                *(["executor-registry"] if self.registry_checked else []),
                *(["executor-config"] if self.config_checked else []),
            ],
            "notChecked": [
                *([] if self.registry_checked else ["executor-registry"]),
                "live-connectivity",
                *([] if self.config_checked else ["executor-config"]),
                "credentials",
                "authorization",
                "sandbox-enforcement",
                "human-channel-delivery",
                "business-quality",
            ],
            "planDigests": self.plan_digests,
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
        }


def preflight_package(
    package_dir: Path,
    *,
    binding_path: Path,
    executor_registry: ExecutorRegistry | None = None,
) -> PreflightReport:
    """Check every workflow against one registry snapshot without I/O to executors.

    A successful report is not a dispatch authorization or a live health probe.
    The Runner still performs its own checks at execution time.
    """
    registry = (executor_registry or local_executor_registry()).snapshot()
    result = compile_package(
        package_dir,
        binding_path=binding_path,
        executor_registry=registry,
    )
    if not result.ok:
        return PreflightReport(tuple(result.diagnostics), {})

    # Recheck the content digest so edits between compilation and registry checks
    # cannot silently combine two different Binding revisions in one report.
    try:
        binding = BindingSet.model_validate(load_document(binding_path).value)
    except (DiagnosticError, ValidationError):
        return _binding_changed(binding_path)
    digest = binding_digest(binding.model_dump(mode="json", by_alias=True, exclude_none=True))
    if any(plan.binding_digest != digest for plan in result.plans.values()):
        return _binding_changed(binding_path)

    diagnostics: list[Diagnostic] = []
    config_checked = True
    for workflow_id, plan in sorted(result.plans.items()):
        checks = registry.preflight_result(nodes=plan.nodes, binding=binding)
        config_checked = config_checked and checks.config_checked
        for issue in checks.issues:
            slot = plan.nodes[issue.node_id]["definition"]["slot"]
            escaped_slot = slot.replace("~", "~0").replace("/", "~1")
            diagnostics.append(
                Diagnostic(
                    code=issue.code,
                    file=str(binding_path.resolve()),
                    pointer=(
                        f"/spec/slots/{escaped_slot}/config{issue.config_pointer}"
                        if issue.config_pointer is not None
                        else f"/spec/slots/{escaped_slot}/executorRef"
                    ),
                    message=issue.message,
                    suggestion=_SUGGESTIONS.get(issue.code, "修复 Binding 并重新运行预检。"),
                    details={
                        "workflowId": workflow_id,
                        "nodeId": issue.node_id,
                        "slot": slot,
                        "source": plan.source_map[issue.node_id],
                        **(
                            {"expected": issue.expected, "actual": issue.actual}
                            if issue.config_pointer is not None
                            else {}
                        ),
                    },
                )
            )
    return PreflightReport(
        tuple(diagnostics),
        {
            workflow_id: plan.compiled_plan_digest
            for workflow_id, plan in sorted(result.plans.items())
        },
        registry_checked=True,
        config_checked=config_checked,
    )


def _binding_changed(binding_path: Path) -> PreflightReport:
    return PreflightReport(
        (
            Diagnostic(
                code="BINDING_CHANGED_DURING_PREFLIGHT",
                file=str(binding_path.resolve()),
                pointer="",
                message="Binding 在预检期间发生变化。",
                suggestion="停止并发编辑后重新预检；不要使用混合版本的结果。",
            ),
        ),
        {},
    )
