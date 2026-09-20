# Repeat Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a bounded `repeat` node through independently persisted child scopes and return its final child output to the parent workflow.

**Architecture:** Persist each scope's immutable input and terminal output in the ledger. The Runner creates a parent invocation for the repeat node, creates one child scope per iteration, evaluates `until` against the completed child output, and either completes, schedules feedback for the next child scope, or records `LOOP_LIMIT_EXCEEDED`.

**Tech Stack:** Python 3.12, SQLite, Pydantic protocol models, JSON Schema, pytest.

---

### Task 1: Prove repeat is not executable

**Files:**
- Modify: `tests/runtime/test_runner.py`

- [x] **Step 1: Write failing runtime tests**

```python
def test_repeat_runs_each_iteration_in_an_independent_scope(...):
    ...
    assert finished["status"] == "succeeded"
    assert [json.loads(scope["path_json"]) for scope in scopes] == [
        ["root"],
        ["root", "repair", "1"],
        ["root", "repair", "2"],
    ]

def test_repeat_fails_when_the_iteration_limit_is_reached(...):
    ...
    assert json.loads(failed["error_json"])["code"] == "LOOP_LIMIT_EXCEEDED"
```

- [x] **Step 2: Run tests and verify the current Runner rejects `repeat`**

Run: `uv run pytest -q tests/runtime/test_runner.py -k repeat`

Expected: FAIL with `unsupported runtime node type: repeat`.

### Task 2: Persist child scope state

**Files:**
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Test: `tests/runtime/test_runner.py`

- [x] **Step 1: Add immutable scope input and terminal output/error fields**

```python
def create_scope(..., input_value: Any, ...) -> dict[str, Any]: ...
def finish_scope(scope_id: str, *, status: str, output: Any = None, error: Any = None) -> dict[str, Any]: ...
def list_scopes(run_id: str) -> list[dict[str, Any]]: ...
```

- [x] **Step 2: Run the focused tests**

Run: `uv run pytest -q tests/runtime/test_runner.py -k repeat`

Expected: still FAIL because `Runner._drive` has no repeat branch.

### Task 3: Drive repeat child scopes

**Files:**
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Test: `tests/runtime/test_runner.py`

- [x] **Step 1: Pass scope-local input and outputs into expression resolution**

```python
input_value = json.loads(scope["input_json"])
node_outputs = self._outputs(scope_id)
```

- [x] **Step 2: Implement repeat lifecycle**

```python
if node["type"] == "repeat":
    # Create one parent invocation and one child scope per iteration.
    # Evaluate until only after a child scope succeeds.
    # Use feedback only when continuing.
    # Finish with LOOP_LIMIT_EXCEEDED after the final unsuccessful iteration.
```

- [x] **Step 3: Support `iteration.output` and `iteration.index` references only for repeat evaluation**

```python
self._predicate(node["until"], input_value, node_outputs, iteration=iteration)
self._resolve_expr(node["feedback"], input_value, node_outputs, iteration=iteration)
```

- [x] **Step 4: Run focused tests**

Run: `uv run pytest -q tests/runtime/test_runner.py -k repeat`

Expected: PASS.

### Task 4: Verify the milestone

**Files:**
- Modify: `docs/authoring/AUTHORING_GUIDE.md`

- [x] **Step 1: Record the new supported Runtime boundary**

Describe bounded sequential repeat as supported only after tests demonstrate it; keep parallel and nested workflow explicitly unsupported.

- [x] **Step 2: Run full verification**

Run:

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy
git diff --check
```

Expected: all commands exit with status 0.

- [x] **Step 3: Commit and push the verified milestone**

```bash
git commit -m "feat: execute bounded repeat workflows"
git push origin dev
```
