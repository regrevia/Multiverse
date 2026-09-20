# Worker-Driven Attempt Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HTTP Attempt reconciliation persist the provider conclusion and a durable continuation wake, while the local Worker performs all downstream workflow progression.

**Architecture:** Keep direct `Runner.reconcile_attempt()` synchronous for CLI and embedded callers. Add an explicit non-resuming path that performs the existing definition, schema, evidence, and version gates, then atomically persists the reconciliation fact and a unique `attempt-reconcile:<attempt-id>` wait. Extend `Runner.sweep()` to claim that wait and invoke the existing reconciliation continuation exactly once by persisted state. Service command receipts report that the reconciliation command was durably accepted; they do not imply that the Run has completed.

**Tech Stack:** Python 3.12, SQLite, Pydantic 2, FastAPI, pytest, Ruff, mypy.

---

### Task 1: Lock the HTTP asynchronous boundary with failing tests

**Files:**
- Modify: `tests/runtime/test_async_dispatch.py`
- Modify: `tests/service/test_application.py`
- Modify: `tests/api/test_app.py`
- Modify: `tests/runtime/test_worker.py`

- [x] **Step 1: Add a service test proving reconciliation does not drive the workflow**

Create an unknown producer attempt, monkeypatch the application Runner's `_apply_reconciled_attempt`, call `RuntimeApplication.reconcile_attempt`, and assert the command completes while the patch was not called, the attempt contains reconciliation JSON, and a pending wait exists at `attempt-reconcile:<attempt-id>`.

- [x] **Step 2: Add a Worker test for confirmed success**

After the service call, assert the Run has not advanced during the HTTP call. Sweep one Worker cycle and assert the same invocation becomes succeeded, downstream nodes are created, and the reconciliation wait is completed.

- [x] **Step 3: Add failure, restart, and idempotency tests**

Cover confirmed failure being applied only by Worker, closing and reopening the application before the sweep, and replaying the same idempotency key returning the same command without creating a second Attempt or wait.

- [x] **Step 4: Run the focused tests and verify they fail for the intended reason**

The new tests first failed for the intended reasons: the service called
`_apply_reconciled_attempt()` synchronously and no Attempt reconciliation wait
was created. After implementation, the focused async/worker tests passed.

### Task 2: Atomically persist reconciliation facts and the Worker wake

**Files:**
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Test: `tests/runtime/test_ledger.py`

- [x] **Step 1: Add a Ledger regression test for the unique reconciliation wait**

Call the new non-resuming Ledger operation twice with the same Attempt and assert the Attempt version and reconciliation JSON remain unchanged on the second call and exactly one pending wait with kind `attempt-reconcile` exists.

- [x] **Step 2: Implement the atomic Ledger operation**

Within one SQLite transaction, validate the expected Attempt version and `unknown` status, update the Attempt with the normalized conclusion/output/error and audit event, then `INSERT ... SELECT` the unique wait with payload containing `attemptId`, `runId`, `scopeId`, `invocationId`, and the updated Attempt version. Treat an existing wait as success only when it references the same Attempt; never create a second wake.

- [x] **Step 3: Run Ledger tests**

Run `uv run pytest tests/runtime/test_ledger.py -q` and confirm the new atomic persistence tests pass without changing existing synchronous Ledger behavior.

### Task 3: Add explicit Runner non-resuming reconciliation

**Files:**
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Test: `tests/runtime/test_runner.py`

- [x] **Step 1: Add a Runner test for `resume=False`**

Call `Runner.reconcile_attempt(..., resume=False)` and assert it returns the reconciled Attempt, does not call `_apply_reconciled_attempt`, and leaves the reconciliation wait pending. Preserve existing tests using the default `resume=True` synchronous behavior.

- [x] **Step 2: Implement the minimal API change**

Add `resume: bool = True` to `Runner.reconcile_attempt()`. Keep all validation before persistence. Use the atomic Ledger operation and return immediately when `resume=False`; otherwise call `_apply_reconciled_attempt()` as before. Make `resume_reconciled_attempt()` idempotent when the Invocation/Run was already advanced.

- [x] **Step 3: Extend `Runner.sweep()`**

Recognize `attempt-reconcile`, validate the payload Attempt ID, call `resume_reconciled_attempt()`, complete the claimed wait only after continuation succeeds, and release the wait on failure. Return wait kind, Attempt ID, Run ID, and resulting status.

- [x] **Step 4: Run Runner and Worker tests**

Run `uv run pytest tests/runtime/test_runner.py tests/runtime/test_worker.py tests/runtime/test_async_dispatch.py -q`.

### Task 4: Decouple the Service/API command path and document the boundary

**Files:**
- Modify: `src/multiverse_workflow/service/application.py`
- Modify: `tests/service/test_application.py`
- Modify: `tests/api/test_app.py`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-09-21-worker-driven-attempt-reconciliation.md`

- [x] **Step 1: Use `resume=False` for first and replayed reconciliation commands**

The service must call `Runner.reconcile_attempt(..., resume=False)`. For an accepted command whose reconciliation fact is already present, return the durable command receipt without applying the continuation. Do not use a read/replay request to execute `_apply_reconciled_attempt()` on the HTTP path.

- [x] **Step 2: Update API assertions**

Keep `202` and command receipt assertions, then explicitly sweep the configured Worker and assert the resulting Run status. Assert that a request returning before the sweep does not claim workflow completion.

- [x] **Step 3: Document verified support and unsupported boundaries**

Record that local SQLite HTTP reconciliation is durable and Worker-driven, while remote Job/Connector lookup, PostgreSQL, multiple active Workers, and real external side-effect reconciliation remain unsupported.

- [x] **Step 4: Run the complete verification set**

Run:

```bash
uv run pytest tests/runtime/test_async_dispatch.py tests/runtime/test_runner.py tests/service/test_application.py tests/api/test_app.py -q
uv run pytest -q
uv run ruff check src tests
uv run mypy
git diff --check
```

Observed evidence before the final commit:

```text
focused async/service/API/Runner/Worker/Ledger tests: 99 passed
uv run pytest -q: 177 passed
uv run ruff check src tests: All checks passed!
uv run mypy: Success: no issues found in 27 source files
git diff --check: passed
```

### Task 5: Commit and push the verified milestone

**Files:**
- Modify: `docs/superpowers/plans/2026-09-21-worker-driven-attempt-reconciliation.md`

- [x] **Step 1: Record actual evidence and remaining limitations**

Replace the verification checkboxes with the actual command results and explicitly separate tested, untested, failed, and unsupported capabilities.

- [ ] **Step 2: Commit the implementation**

```bash
git add src tests README.md docs/superpowers/plans/2026-09-21-worker-driven-attempt-reconciliation.md
git commit -m "feat: make attempt reconciliation worker-driven"
```

- [ ] **Step 3: Push and verify the remote branch**

```bash
git push origin dev
git rev-parse HEAD
git ls-remote origin refs/heads/dev
git status --short --branch
```

Do not add `inspector/pnpm-lock.yaml` or `inspector/pnpm-workspace.yaml`.
