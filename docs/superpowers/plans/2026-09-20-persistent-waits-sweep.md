# Persistent Waits And Recovery Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local SQLite workflow waits durable and recoverable by a worker sweep after restart, without requiring a repeated client command or duplicating a HumanDecision transition.

**Architecture:** Add a single `waits` ledger table for human and retry waits with semantic unique keys. Human request creation and decision completion update the wait record in their existing transactions. Runner exposes a bounded `sweep()` that claims due retry waits and pending human-progress intents, rechecks current state, and resumes only the original Run/Invocation.

**Tech Stack:** Python 3.12, SQLite, existing `Ledger`, `Runner`, pytest, ruff, mypy.

---

### Task 1: Define durable wait records with a failing ledger test

**Files:**
- Modify: `tests/runtime/test_ledger.py`
- Modify: `src/multiverse_workflow/runtime/ledger.py`

- [x] **Step 1: Write the failing test** for creating, listing, claiming, and completing a wait by its semantic key.
- [x] **Step 2: Run the focused test** and confirm the missing wait API fails.
- [x] **Step 3: Add the SQLite schema and minimal Ledger methods** with a unique `(namespace, wait_key)` identity and due-time filtering.
- [x] **Step 4: Run the focused test** and confirm it passes.

### Task 2: Attach waits atomically to HumanRequest and retry scheduling

**Files:**
- Modify: `tests/runtime/test_ledger.py`
- Modify: `tests/runtime/test_runner.py`
- Modify: `src/multiverse_workflow/runtime/ledger.py`

- [x] **Step 1: Add assertions** that a HumanRequest creates a pending wait and a decision completes it.
- [x] **Step 2: Add assertions** that retry scheduling creates a due wait and cancellation removes it from due work.
- [x] **Step 3: Run the focused tests** and confirm they fail before integration.
- [x] **Step 4: Update the existing transactions** so wait state and audit state commit together.
- [x] **Step 5: Run the focused tests** and confirm they pass.

### Task 3: Add Runner sweep and restart coverage

**Files:**
- Modify: `tests/runtime/test_runner.py`
- Modify: `tests/service/test_application.py`
- Modify: `src/multiverse_workflow/runtime/runner.py`

- [x] **Step 1: Add a failing test** that closes and reopens a runtime, then calls `sweep()` to resume a due retry without a second client request.
- [x] **Step 2: Add a failing test** that leaves a completed HumanDecision progress intent pending and verifies `sweep()` finishes the same Run once.
- [x] **Step 3: Implement bounded sweep dispatch** with state rechecks and stable scope/invocation identities.
- [x] **Step 4: Run focused recovery tests** and confirm they pass with no duplicate `human.decided` or downstream events.

### Task 4: Update local preview documentation and verify

**Files:**
- Modify: `README.md`
- Modify: `tests/cli/test_runtime.py`

- [x] **Step 1: Document the local `sweep()`/worker recovery boundary** without claiming multi-worker or external outbox support.
- [x] **Step 2: Add a CLI smoke assertion** for the recovery entrypoint.
- [ ] **Step 3: Run `uv run pytest -q`, `uv run ruff check src tests`, `uv run mypy`, and `git diff --check`.
- [ ] **Step 4: Commit and push the verified milestone to `origin/dev`.
