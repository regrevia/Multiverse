# Local Run Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persisted local pause, resume, cancel, and rerun commands without allowing a decision or late continuation to bypass the Run control intent.

**Architecture:** Store the control intent and state transition in the SQLite ledger under optimistic version checks. The Runner checks control intent before dispatching or resuming downstream work. Rerun starts a new Run with the original frozen input and records the source Run reference; it never changes a completed Run or copies its HumanRequest decision.

**Tech Stack:** Python 3.12, SQLite, Typer, pytest.

---

### Task 1: Lock control semantics with failing tests

**Files:**
- Modify: `tests/runtime/test_runner.py`
- Modify: `tests/cli/test_runtime.py`

- [x] **Step 1: Add a paused-decision test**

```python
def test_paused_run_records_a_human_decision_without_dispatching_downstream(...):
    waiting = runner.start({"goal": "ship the release"})
    paused = runner.pause(waiting["id"], expected_version=waiting["version"], reason="hold")
    request = runner.pending_human_requests(waiting["id"])[0]

    decided = runner.decide(...)

    assert decided["status"] == "paused"
    assert runner.resume(decided["id"], expected_version=decided["version"], reason="continue")["status"] == "succeeded"
```

- [x] **Step 2: Add cancel and rerun tests**

```python
def test_cancelled_waiting_run_rejects_late_human_decision(...):
    ...

def test_rerun_creates_an_independent_run_and_human_request(...):
    ...
```

- [x] **Step 3: Run focused tests**

Run:

```bash
uv run pytest -q tests/runtime/test_runner.py -k "paused or cancelled or rerun"
```

Expected: FAIL because `Runner` has no control command methods.

### Task 2: Persist control state transitions

**Files:**
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Test: `tests/runtime/test_ledger.py`

- [x] **Step 1: Add a version-checked control transition**

```python
def control_run(
    self,
    run_id: str,
    *,
    operation: Literal["pause", "resume", "cancel"],
    expected_version: int,
    reason: str,
) -> dict[str, Any]:
    ...
```

Pause transitions an active Run to `control_mode="pause"` and `status="paused"`.
Resume only accepts `control_mode="pause"` and returns the Run to `running`.
Cancel marks pending HumanRequests, waiting Attempts, waiting Invocations, and
active Scopes as cancelled before storing `control_mode="cancel"` and
`status="cancelled"`.

- [x] **Step 2: Store rerun provenance**

Add nullable `rerun_of` and `rerun_reason` columns to `runs`, including
additive migration checks for existing SQLite files. Extend `create_run()` to
write both values.

- [x] **Step 3: Run ledger tests**

Run:

```bash
uv run pytest -q tests/runtime/test_ledger.py
```

Expected: PASS.

### Task 3: Gate Runtime progression and expose commands

**Files:**
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Modify: `src/multiverse_workflow/cli/main.py`
- Modify: `tests/runtime/test_runner.py`
- Modify: `tests/cli/test_runtime.py`

- [x] **Step 1: Add Runner command methods**

```python
def pause(self, run_id: str, *, expected_version: int, reason: str) -> dict[str, Any]: ...
def resume(self, run_id: str, *, expected_version: int, reason: str) -> dict[str, Any]: ...
def cancel(self, run_id: str, *, expected_version: int, reason: str) -> dict[str, Any]: ...
def rerun(self, run_id: str, *, reason: str, input_value: Any | None = None) -> dict[str, Any]: ...
```

`resume()` calls `_drive()` only after the persisted resume transition. `_drive()`
returns without dispatching when the control mode is `pause` or `cancel`.
`decide()` stores a valid human result while paused but leaves the Run paused
until `resume()` re-enters the same persisted node. `rerun()` rejects a
non-terminal source Run and starts a new Run with the original workflow/input.

- [x] **Step 2: Add CLI commands**

```bash
mverse pause <run-id> --expected-version <n> --reason "..."
mverse resume <run-id> --expected-version <n> --reason "..."
mverse cancel <run-id> --expected-version <n> --reason "..."
mverse rerun <run-id> --reason "..."
```

Each command returns the persisted Run JSON and uses exit code `3` for a
version or lifecycle conflict.

- [x] **Step 3: Run focused Runtime and CLI tests**

Run:

```bash
uv run pytest -q tests/runtime/test_runner.py -k "paused or cancelled or rerun"
uv run pytest -q tests/cli/test_runtime.py
```

Expected: PASS.

### Task 4: Verify and publish the milestone

**Files:**
- Modify: `README.md`
- Modify: `docs/authoring/AUTHORING_GUIDE.md`

- [x] **Step 1: Document exact preview scope**

State that local SQLite Run controls have version checks and that they only
cover locally persisted HumanRequests. Keep asynchronous execution control,
HTTP command receipts, external cancellation, and worker recovery marked
unsupported.

- [x] **Step 2: Run full verification**

Run:

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy
git diff --check
```

Expected: all commands exit with status 0.

- [x] **Step 3: Commit and push**

```bash
git add README.md docs/authoring/AUTHORING_GUIDE.md \
  docs/superpowers/plans/2026-09-20-local-run-controls.md \
  src/multiverse_workflow/runtime/ledger.py \
  src/multiverse_workflow/runtime/runner.py \
  src/multiverse_workflow/cli/main.py \
  tests/runtime/test_ledger.py \
  tests/runtime/test_runner.py \
  tests/cli/test_runtime.py
git commit -m "feat: add local run controls"
git push origin dev
```
