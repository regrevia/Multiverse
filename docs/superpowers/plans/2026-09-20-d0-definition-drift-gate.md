# D0 Definition Drift Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent a persisted Run from continuing with a changed Package or Binding after a new Runner process is constructed.

**Architecture:** The ledger already stores the package and binding digests used when a Run was created. Before `Runner.decide()` completes a persisted human decision and calls `_drive`, compare those stored digests with the current compiled plan for that workflow. A mismatch raises an explicit `RunError`; unchanged definitions retain the existing behavior.

**Tech Stack:** Python 3.12, SQLite ledger, pytest.

---

### Task 1: Lock a restart-and-drift regression test

**Files:**
- Modify: `tests/runtime/test_runner.py`

- [x] **Step 1: Write the failing test**

```python
def test_resume_blocks_a_binding_digest_that_changed_after_run_start(tmp_path: Path) -> None:
    binding = tmp_path / "binding.yaml"
    binding.write_text(
        (ROOT / "examples/bindings/content-local.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    database = tmp_path / "runtime.db"
    first = Runner(ROOT / "presets/content-delivery", binding_path=binding, database_path=database)
    waiting = first.start({"goal": "prepare a release"})
    request = first.pending_human_requests(waiting["id"])[0]

    binding.write_text(
        binding.read_text(encoding="utf-8").replace("version: 0.1.0", "version: 0.1.1"),
        encoding="utf-8",
    )
    resumed = Runner(ROOT / "presets/content-delivery", binding_path=binding, database_path=database)

    with pytest.raises(RunError, match="runtime definition drift.*binding digest"):
        resumed.decide(
            request["id"],
            choice="approve",
            comment="Approved.",
            actor="example-reviewer",
            subject_digest=request["subject_digest"],
            expected_version=request["version"],
        )
```

- [x] **Step 2: Run it and observe current unsafe continuation**

Run: `uv run pytest tests/runtime/test_runner.py::test_resume_blocks_a_binding_digest_that_changed_after_run_start -q`

Expected: FAIL because the current `decide()` uses the current compiled plan.

### Task 2: Block definition drift before continuation

**Files:**
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Modify: `tests/runtime/test_runner.py`

- [x] **Step 1: Add the minimal pre-continuation check**

```python
def _require_matching_definition(
    self,
    run: dict[str, Any],
    plan: ExecutionPlan,
) -> None:
    if run["package_digest"] != plan.package_digest:
        raise RunError("runtime definition drift: package digest changed")
    if run["binding_digest"] != plan.binding_digest:
        raise RunError("runtime definition drift: binding digest changed")
```

Call it in `decide()` after loading the Run and current plan, but before recording the human decision or calling `_drive`.

- [x] **Step 2: Verify focused and full checks**

Run:

```bash
uv run pytest tests/runtime/test_runner.py -q
uv run pytest -q
uv run ruff check src tests
uv run mypy
git diff --check
```

Expected: all commands exit with code 0.

- [x] **Step 3: Commit and push**

```bash
git add \
  docs/superpowers/plans/2026-09-20-d0-definition-drift-gate.md \
  src/multiverse_workflow/runtime/runner.py \
  tests/runtime/test_runner.py
git commit -m "fix: block resumed runs on definition drift"
git push origin dev
```
