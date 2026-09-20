# Async Runtime Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local HTTP Runtime accept durable Run and human-decision commands without executing the workflow on the request path; the single-active Worker performs the continuation.

**Architecture:** Keep synchronous `Runner.start()` and CLI behavior for local direct runs. Add an enqueue path that persists a queued Run with its frozen plan and root continuation, and extend the existing wait sweep to claim `run-start` work. Service-layer Run creation and HumanDecision submission use the enqueue/non-resuming Runner paths; the Worker resumes the same persisted Run and existing human-progress intent. Queue scans remain a recovery fallback for a crash before the start wake is written.

**Tech Stack:** Python 3.12, SQLite, existing Ledger/Runner/LocalWorker, FastAPI, httpx, pytest.

---

### Task 1: Add failing tests for asynchronous HTTP semantics

**Files:**
- Modify: `tests/service/test_application.py`
- Modify: `tests/api/test_app.py`
- Modify: `tests/e2e/test_service_workflow.py`
- Create: `tests/runtime/test_async_dispatch.py`

- [x] **Step 1: Test service Run creation returns queued without invoking `_drive`**
- [x] **Step 2: Test Worker resumes the same queued Run to the first human wait**
- [x] **Step 3: Test HTTP human decision returns while Run remains waiting, then Worker finishes it**
- [x] **Step 4: Test repeated HTTP create with the same key does not create a second Run**
- [x] **Step 5: Run focused tests and observe failures caused by synchronous `Runner.start()`/`decide()`**

```bash
uv run pytest tests/service/test_application.py tests/api/test_app.py tests/e2e/test_service_workflow.py tests/runtime/test_async_dispatch.py -q
```

### Task 2: Add durable queued Run continuation

**Files:**
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Modify: `src/multiverse_workflow/runtime/worker.py`
- Test: `tests/runtime/test_async_dispatch.py`

- [x] **Step 1: Add `Runner.enqueue()`**

Validate the selected workflow input and full reachable execution plan using the same gates as `start()`, persist the frozen plan and root scope, leave the Run `queued`, and write a `run-start` wait with key `run-start:<run-id>`.

- [x] **Step 2: Add `Runner.resume_queued()`**

Recover a queued Run with its persisted scope and node. If the process stopped after the Run became `running`, re-enter the persisted continuation; if the Run is already waiting or terminal, return it without replaying work.

- [x] **Step 3: Extend `Runner.sweep()`**

Claim `run-start` waits and call `resume_queued()`. Complete the wait after the same Run reaches a durable state; release it on an exception. Do not create a second Run or Attempt.

- [x] **Step 4: Add queued-run fallback scanning**

Expose a bounded Ledger query for `queued` Runs in the namespace and let `LocalWorker.run_once()` recover queued Runs that have no start wait because the process stopped between the Run transaction and wake creation.

- [x] **Step 5: Add the resume wake for non-synchronous control**

When the service uses the non-resuming `Runner.resume()` path, persist a `run-resume` wait in the control transaction. The Worker handles it through the same persisted continuation.

### Task 3: Decouple service commands from workflow driving

**Files:**
- Modify: `src/multiverse_workflow/service/application.py`
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Test: `tests/service/test_application.py`

- [x] **Step 1: Use `Runner.enqueue()` in `RuntimeApplication.create_run()`**

Return a completed command receipt for the accepted durable command, with the Run resource still `queued`. Idempotent replay returns the same command and Run.

- [x] **Step 2: Add a `resume` flag to human decision processing**

Keep `Runner.decide(..., resume=True)` as the synchronous CLI/default path. Service calls `resume=False`, so it commits the decision and existing `human-progress` wait without calling `_drive()`.

- [x] **Step 3: Use the non-resuming decision path in `RuntimeApplication.decide_human_request()`**

The HTTP request returns the same Run reference and current version; the Worker performs downstream execution.

- [x] **Step 4: Use the non-resuming resume path in `RuntimeApplication.control_run()`**

Preserve CLI synchronous resume while service resume only records control state and the durable `run-resume` wake.

### Task 4: Update API/e2e documentation and verification

**Files:**
- Modify: `tests/api/test_app.py`
- Modify: `tests/e2e/test_service_workflow.py`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-09-20-async-runtime-dispatch.md`

- [x] **Step 1: Update API tests to start the local Worker explicitly**

Assert `POST /runs` returns `resourceId` with `queued`, then run one Worker cycle and assert `waiting`.

- [x] **Step 2: Update decision tests**

Assert the decision receipt is returned before downstream execution, then run Worker and assert `succeeded`.

- [x] **Step 3: Document the two-process local preview**

Show `mverse serve` and `mverse worker` as separate processes. Explain that HTTP disconnect does not cancel a queued Run, and that the SQLite profile remains single-active Worker.

- [x] **Step 4: Run focused, full, lint, and type verification**

```bash
uv run pytest tests/runtime/test_async_dispatch.py tests/service/test_application.py tests/api/test_app.py tests/e2e/test_service_workflow.py -q
uv run pytest -q
uv run ruff check src tests
uv run mypy
```

### Task 5: Commit and push the verified milestone

**Files:**
- Modify: `docs/superpowers/plans/2026-09-20-async-runtime-dispatch.md`

- [x] **Step 1: Record actual command output and remaining unsupported boundaries**

Verification evidence for this milestone:

```text
uv run pytest tests/runtime/test_async_dispatch.py tests/service/test_application.py tests/api/test_app.py tests/e2e/test_service_workflow.py -q
31 passed

uv run pytest -q
173 passed

uv run ruff check src tests
All checks passed!

uv run mypy
Success: no issues found in 27 source files
```

The local service now has a real two-process boundary: HTTP commits the Run
and command, while the single-active SQLite Worker executes queued and resumed
continuations. Unsupported boundaries remain PostgreSQL, multiple active
Workers, distributed queues, remote Connector/HTTP Job execution, and unknown
external side-effect reconciliation.
- [ ] **Step 2: Commit**

```bash
git add src tests README.md docs/superpowers/plans/2026-09-20-async-runtime-dispatch.md
git commit -m "feat: decouple HTTP runs from workflow execution"
```

- [ ] **Step 3: Push and verify**

```bash
git push origin dev
git rev-parse HEAD
git ls-remote origin refs/heads/dev
git status --short --branch
```

Do not add the existing untracked Inspector lock/workspace files to this
milestone.
