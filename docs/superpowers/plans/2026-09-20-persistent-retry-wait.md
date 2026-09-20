# Persistent Retry Wait Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist runtime retry waits and resume eligible Attempts after a process restart without blocking the request thread.

**Architecture:** Store `next_attempt_at` on the Run and Attempt records. The Ledger atomically records the failed Attempt, retry-wait Invocation, timer, and audit events. Runner exposes an explicit `resume_due(run_id)` recovery entrypoint and creates the next Attempt only after the persisted timer is due.

**Tech Stack:** Python 3.12, SQLite, pytest, Ruff, mypy.

---

### Task 1: Persist retry scheduling

**Files:**
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Test: `tests/runtime/test_runner.py`

- [x] **Step 1:** Add `next_attempt_at` columns and migrate existing databases.
- [x] **Step 2:** Add an atomic Ledger operation that records failed Attempt state, retry-wait Invocation/Run state, timer, and events.
- [x] **Step 3:** Add `Runner.resume_due(run_id)` and create the next Attempt only when the persisted timer is due.

### Task 2: Verify restart behavior

- [x] **Step 1:** Add a regression test for not-due retry waits surviving restart.
- [x] **Step 2:** Add a regression test for due retry waits creating a new Attempt and continuing execution.
- [x] **Step 3:** Run `uv run pytest -q`, `uv run ruff check src tests`, `uv run mypy`, and `git diff --check`.

### Task 3: Commit and push

- [x] **Step 1:** Commit with `feat: persist runtime retry waits`.
- [x] **Step 2:** Push `origin/dev` and verify local and remote commit IDs match.
