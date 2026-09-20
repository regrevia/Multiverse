# D0 Runtime Capability Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an internal executor registry and reject unavailable execution bindings before a Run records or dispatches business work.

**Architecture:** Keep the public `BindingSet` adapter enum unchanged. Move the local executor metadata from the compiler into an immutable internal registry shared by Compiler, CLI capability output, and Runner. The Runner snapshots that registry during construction, then preflights every `call` node of the selected execution plan before it creates a Run or Scope.

**Tech Stack:** Python 3.12, Pydantic protocol models, SQLite ledger, pytest, Typer.

---

## File Structure

- Create: `src/multiverse_workflow/runtime/registry.py`
  - Immutable executor descriptors, support-state catalog generation, and structured preflight issues.
- Modify: `src/multiverse_workflow/compiler/compiler.py`
  - Read descriptor metadata from the registry rather than maintaining a compiler-local table.
- Modify: `src/multiverse_workflow/runtime/runner.py`
  - Snapshot the registry and gate the selected plan before `Ledger.create_run`.
- Create: `tests/runtime/test_registry.py`
  - Unit tests for support reporting and no-side-effect preflight failure.
- Modify: `tests/cli/test_validate.py`
  - Preserve the capability catalog contract through the CLI.

### Task 1: Define the internal registry

**Files:**
- Create: `src/multiverse_workflow/runtime/registry.py`
- Test: `tests/runtime/test_registry.py`

- [x] **Step 1: Write the failing support-state test**

```python
from multiverse_workflow.runtime.registry import local_executor_registry


def test_local_registry_reports_declared_installed_available_and_verified_separately() -> None:
    catalog = {
        item["executorRef"]: item
        for item in local_executor_registry().capability_catalog()
    }

    assert catalog["builtin.human-input.v1"]["available"] is True
    assert catalog["example.remote-content.v1"]["declared"] is True
    assert catalog["example.remote-content.v1"]["installed"] is False
    assert catalog["example.remote-content.v1"]["available"] is False
    assert catalog["example.remote-content.v1"]["verified"] is False
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/runtime/test_registry.py::test_local_registry_reports_declared_installed_available_and_verified_separately -q`

Expected: FAIL because `multiverse_workflow.runtime.registry` does not exist.

- [x] **Step 3: Add immutable descriptors and catalog generation**

```python
@dataclass(frozen=True)
class ExecutorDescriptor:
    executor_ref: str
    adapter: str
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


class ExecutorRegistry:
    def __init__(self, descriptors: Iterable[ExecutorDescriptor]) -> None:
        self._descriptors = {descriptor.executor_ref: descriptor for descriptor in descriptors}

    def resolve(self, executor_ref: str) -> ExecutorDescriptor | None:
        return self._descriptors.get(executor_ref)

    def snapshot(self) -> ExecutorRegistry:
        return ExecutorRegistry(self._descriptors.values())

    def capability_catalog(self) -> list[dict[str, object]]:
        return [
            descriptor.as_catalog_entry()
            for _, descriptor in sorted(self._descriptors.items())
        ]
```

Populate the registry with the five existing local descriptors. Mark the remote fixture declared but not installed, available, or verified.

- [x] **Step 4: Run the focused test to verify it passes**

Run: `uv run pytest tests/runtime/test_registry.py::test_local_registry_reports_declared_installed_available_and_verified_separately -q`

Expected: PASS.

### Task 2: Route Compiler and CLI capability output through the registry

**Files:**
- Modify: `src/multiverse_workflow/compiler/compiler.py`
- Modify: `tests/cli/test_validate.py`
- Test: `tests/compiler/test_compile_package.py`

- [x] **Step 1: Write the failing catalog identity test**

```python
from multiverse_workflow.compiler import executor_capabilities
from multiverse_workflow.runtime.registry import local_executor_registry


def test_compiler_capability_catalog_uses_local_executor_registry() -> None:
    assert executor_capabilities() == local_executor_registry().capability_catalog()
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/cli/test_validate.py::test_compiler_capability_catalog_uses_local_executor_registry -q`

Expected: FAIL because the compiler still owns its local descriptor table.

- [x] **Step 3: Replace compiler-local descriptor tables**

```python
from multiverse_workflow.runtime.registry import local_executor_registry


def executor_capabilities() -> list[dict[str, object]]:
    return local_executor_registry().capability_catalog()
```

In `_validate_binding`, resolve an executor with `local_executor_registry().resolve(slot.executor_ref)`, retain the existing diagnostic codes and messages, and compare `slot.adapter` and node capabilities against the returned descriptor.

- [x] **Step 4: Run compiler and CLI capability tests**

Run: `uv run pytest tests/compiler/test_compile_package.py tests/cli/test_validate.py -q`

Expected: PASS, including existing unresolved-executor and adapter-mismatch diagnostics.

### Task 3: Preflight the selected plan before recording a Run

**Files:**
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Modify: `tests/runtime/test_runner.py`
- Test: `tests/runtime/test_registry.py`

- [x] **Step 1: Write the failing no-side-effect preflight test**

```python
import sqlite3

import pytest

from multiverse_workflow.runtime.runner import RunError, Runner


def test_unavailable_binding_is_rejected_before_a_run_is_recorded(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    runner = Runner(
        ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-remote.yaml",
        database_path=database,
    )

    with pytest.raises(RunError, match="EXECUTOR_UNAVAILABLE.*example.remote-content.v1"):
        runner.start({"goal": "do not dispatch remote work"})

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
```

- [x] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/runtime/test_runner.py::test_unavailable_binding_is_rejected_before_a_run_is_recorded -q`

Expected: FAIL because the current runner creates a Run and then records `EXECUTOR_UNSUPPORTED`.

- [x] **Step 3: Add frozen plan preflight**

```python
def start(self, input_value: Any, workflow_id: str | None = None) -> dict[str, Any]:
    workflow_id = workflow_id or next(iter(self._plans))
    plan = self._plan(workflow_id)
    self._preflight_execution(plan)
    workflow = self._workflows[workflow_id]
    ...

def _preflight_execution(self, plan: ExecutionPlan) -> None:
    issues = self._executor_registry.preflight_plan(
        plan=plan,
        binding=self._binding,
    )
    if issues:
        raise RunError(
            "runtime preflight failed: "
            + "; ".join(
                f"{issue.code} ({issue.node_id}): {issue.message}"
                for issue in issues
            )
        )
```

Construct `self._executor_registry` by snapshotting the supplied registry or the local default inside `Runner.__init__`. The registry returns `EXECUTOR_UNRESOLVED`, `EXECUTOR_ADAPTER_MISMATCH`, `CAPABILITY_MISMATCH`, `EXECUTOR_NOT_INSTALLED`, `EXECUTOR_UNAVAILABLE`, or `EXECUTOR_UNVERIFIED` issues without dispatching an implementation.

- [x] **Step 4: Run preflight and existing local-flow tests**

Run: `uv run pytest tests/runtime/test_runner.py tests/runtime/test_registry.py -q`

Expected: PASS. The local content-delivery flow still reaches its human request and a remote fixture binding fails before any `runs` row exists.

### Task 4: Run complete verification and commit the D0 slice

**Files:**
- Modify: `docs/superpowers/plans/2026-09-20-d0-runtime-capability-gate.md`

- [x] **Step 1: Mark completed plan items**

Update this file’s checkboxes only after the matching commands pass.

- [x] **Step 2: Run complete checks**

Run:

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy
git diff --check
```

Expected: all commands exit with code 0.

- [x] **Step 3: Commit**

```bash
git add \
  docs/superpowers/plans/2026-09-20-d0-runtime-capability-gate.md \
  src/multiverse_workflow/runtime/registry.py \
  src/multiverse_workflow/compiler/compiler.py \
  src/multiverse_workflow/runtime/runner.py \
  tests/runtime/test_registry.py \
  tests/runtime/test_runner.py \
  tests/cli/test_validate.py
git commit -m "feat: gate runs on registered executor support"
git push origin dev
```
