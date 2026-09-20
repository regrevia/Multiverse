# Attempt Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable, version-checked Attempt reconciliation command for execution results that cannot be safely inferred from a lost response.

**Architecture:** Keep `Ledger` as the transaction authority and expose reconciliation through the existing Application Service and FastAPI command boundary. Reconciliation accepts only the four normative conclusions, stores evidence and the authenticated subject, rejects stale or terminal Attempts, and never performs an arbitrary status patch. A confirmed success is validated by the frozen workflow contract before the Runner resumes downstream progress.

**Tech Stack:** Python 3.12, SQLite, Pydantic 2, FastAPI, Typer, pytest.

---

### Task 1: Freeze reconciliation contracts and persistence behavior

**Files:**
- Modify: `src/multiverse_workflow/service/contracts.py`
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Test: `tests/service/test_contracts.py`
- Test: `tests/runtime/test_ledger.py`

- [x] **Step 1: Write failing tests** for the four conclusions, required evidence, Attempt versioning, and rejection of stale/terminal reconciliation.
- [x] **Step 2: Run the focused tests** and confirm failure because the request model and Ledger methods do not exist.
- [x] **Step 3: Add strict `AttemptReconcileRequest` and `ReconcileConclusion` types**, then add the Attempt `version` column, migration, and one atomic Ledger reconciliation method.
- [x] **Step 4: Run focused contract and Ledger tests** and confirm they pass.

### Task 2: Add Application and HTTP command boundary

**Files:**
- Modify: `src/multiverse_workflow/service/application.py`
- Modify: `src/multiverse_workflow/api/app.py`
- Modify: `tests/service/test_application.py`
- Modify: `tests/api/test_app.py`

- [x] **Step 1: Write failing service/API tests** for authenticated reconcile, namespace isolation, idempotent command receipts, and evidence propagation.
- [x] **Step 2: Implement `RuntimeApplication.reconcile_attempt`** using the configured subject and durable command ledger.
- [x] **Step 3: Add `POST /api/v1/namespaces/{namespace}/attempts/{attempt_id}:reconcile`** with `reconcile:write` scope and the standard error envelope.
- [x] **Step 4: Run focused service/API tests** and confirm they pass.

### Task 3: Resume confirmed execution and expose audit facts

**Files:**
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Modify: `src/multiverse_workflow/runtime/projection.py`
- Modify: `tests/runtime/test_runner.py`
- Modify: `tests/runtime/test_projection.py`
- Modify: `README.md`
- Modify: `docs/authoring/AUTHORING_GUIDE.md`

- [x] **Step 1: Add a regression test** proving confirmed success validates output and resumes the frozen next node without creating a second Attempt.
- [x] **Step 2: Implement Runner reconciliation for confirmed success and terminal failure/cancellation propagation.**
- [x] **Step 3: Include Attempt version, reconciliation evidence, and actor in the read-only projection.**
- [x] **Step 4: Run the full suite, static checks, and update the local service documentation with the exact endpoint and support boundary.**
- [x] **Step 5:** Add regression tests for `confirmed_not_started` retry limits,
  same-Invocation `effectKey` reuse, new `dispatchKey` creation, and pause/cancel
  control intent preservation.
- [x] **Step 6:** Implement `confirmed_not_started` as a bounded retry decision:
  create a new Attempt only while the frozen `maxAttempts` permits it; otherwise
  fail or cancel the Invocation according to the persisted Run control intent.
- [x] **Step 7:** Re-enter the Runner through a persisted Invocation input snapshot
  so a reconciled retry cannot regenerate a different semantic payload.

### Task 4: Harden command receipt scope and legacy migration

**Files:**
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Modify: `src/multiverse_workflow/service/application.py`
- Test: `tests/runtime/test_ledger.py`
- Test: `tests/service/test_application.py`

- [x] **Step 1:** Add failing tests for command lookup isolation by authenticated
  subject and migration from the legacy globally-unique idempotency key.
- [x] **Step 2:** Add the `subject` column and composite
  `namespace + subject + operation + idempotency_key` index migration, then use
  scoped command listing when detecting cross-operation idempotency conflicts.
- [x] **Step 3:** Hide command receipts from a different authenticated subject even
  when the namespace and command ID are known.
- [x] **Step 4:** Run focused ledger and service tests.

### Task 5: Verify and push the milestone

- [x] **Step 1:** Run `uv run pytest -q`.
- [x] **Step 2:** Run `uv run ruff check src tests`, `uv run mypy`, and `git diff --check`.
- [ ] **Step 3:** Commit with `feat: add durable attempt reconciliation`.
- [ ] **Step 4:** Push `origin/dev` and verify the remote branch points to the new commit.
