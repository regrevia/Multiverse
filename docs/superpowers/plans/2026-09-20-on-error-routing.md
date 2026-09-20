# onError Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route determined execution failures through the frozen workflow `onError` edge while exposing the failed node's `{error: ErrorEnvelope}` output.

**Architecture:** Keep the Ledger as the source of failure facts and let Runner decide whether a failed node has an `onError` target. A failed Invocation and Attempt retain the normalized error output; the error route re-enters the same scope only after the failed activity is terminal. Unknown, cancelled, and not-started reconciliation conclusions never use an error route.

**Tech Stack:** Python 3.12, SQLite, Pydantic 2, JSON Schema, pytest.

---

### Task 1: Define runtime error-route behavior with failing tests

**Files:**
- Modify: `tests/runtime/test_runner.py`

- [x] **Step 1:** Add a package fixture with a call node whose normal and error edges reach a handler, plus schemas that accept the failed node's error output.
- [x] **Step 2:** Add a failing test proving a determined executor failure marks the failed Invocation with `{error: ErrorEnvelope}`, routes to the handler, and can finish successfully.
- [x] **Step 3:** Add a failing test proving `confirmed_failed` reconciliation uses the same `onError` route, while an unknown Attempt does not route before reconciliation.

### Task 2: Implement error output and routing

**Files:**
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Test: `tests/runtime/test_runner.py`

- [x] **Step 1:** Normalize runtime errors for error-path output without changing existing persisted error-code compatibility.
- [x] **Step 2:** Store failed Attempt/Invocation output as `{error: ErrorEnvelope}` and include failed Invocation outputs in same-scope references.
- [x] **Step 3:** Route determined failures through `onError`; propagate failures through nested scopes and stop at the first scope without an error edge.
- [x] **Step 4:** Keep `confirmed_cancelled` and exhausted `confirmed_not_started` on cancellation/failure propagation, not error routing.

### Task 3: Verify and push

- [x] **Step 1:** Run focused routing tests.
- [x] **Step 2:** Run `uv run pytest -q`, `uv run ruff check src tests`, `uv run mypy`, and `git diff --check`.
- [x] **Step 3:** Commit with `feat: route determined failures through onError`.
- [x] **Step 4:** Push `origin/dev` and verify the remote branch points to the new commit.
