# Persistent Local Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent local SQLite Worker that repeatedly processes durable waits, resumes after a crashed worker, and exposes the `mverse worker` CLI without claiming distributed scheduling.

**Architecture:** Keep `Runner.sweep()` as the bounded, state-aware application operation. Add a small `LocalWorker` lifecycle wrapper that acquires a filesystem lock, requeues stale claimed waits, polls `sweep()`, and supports a deterministic one-cycle mode for tests and local scripts. The CLI constructs this worker from the package, binding, database, namespace, and worker identity.

**Tech Stack:** Python 3.12, SQLite, `fcntl.flock`, Typer, pytest, existing `Runner`/`Ledger`.

---

### Task 1: Define worker lifecycle behavior with failing tests

**Files:**
- Create: `tests/runtime/test_worker.py`
- Modify: `tests/cli/test_runtime.py`

- [x] **Step 1: Add a test for one-cycle processing and a no-op idle cycle**

```python
def test_worker_once_processes_due_waits_and_returns_cycle_result(tmp_path: Path) -> None:
    worker = LocalWorker.from_paths(
        package_dir=ROOT / "presets/content-delivery",
        binding_path=ROOT / "examples/bindings/content-local.yaml",
        database_path=tmp_path / "runtime.db",
        worker_id="test-worker",
    )
    try:
        result = worker.run_once()
        assert result == []
    finally:
        worker.close()
```

- [x] **Step 2: Add a test that a stale claimed wait is recovered after restart**

Create a due human-progress wait, mark it claimed by a prior worker, reopen `LocalWorker` with `claim_timeout_seconds=0`, and assert `run_once()` processes it once and the wait is `completed`.

- [x] **Step 3: Add a test that a second local worker cannot acquire the same lock**

Open one worker, construct a second worker for the same database, and assert `WorkerLockError` before any sweep occurs.

- [x] **Step 4: Add a CLI `worker --once --json` test**

Create a local waiting run, submit the human decision through the existing ledger setup, invoke the CLI worker once, and assert exit code `0`, a JSON cycle payload, the same run id, and no duplicate invocation.

- [x] **Step 5: Run the focused tests and confirm they fail because the Worker API is missing**

Run:

```bash
uv run pytest tests/runtime/test_worker.py tests/cli/test_runtime.py -q
```

Observed first run: collection failed with `ModuleNotFoundError: No module named
'multiverse_workflow.runtime.worker'`.

### Task 2: Add stale wait recovery to the Ledger

**Files:**
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Test: `tests/runtime/test_worker.py`

- [x] **Step 1: Add `requeue_stale_waits(now, older_than, namespace)`**

Update only `waits.status = 'claimed'` rows whose `claimed_at` is older than the cutoff, clear `worker_id` and `claimed_at`, and return the number of rows changed. Never update `completed` or `cancelled` waits.

- [x] **Step 2: Run the stale-wait test and verify it passes**

Run:

```bash
uv run pytest tests/runtime/test_worker.py::test_worker_recovers_stale_claimed_wait_after_restart -q
```

Observed: PASS as part of the focused Worker test run.

### Task 3: Implement the persistent local Worker

**Files:**
- Create: `src/multiverse_workflow/runtime/worker.py`
- Modify: `src/multiverse_workflow/runtime/__init__.py`
- Test: `tests/runtime/test_worker.py`

- [x] **Step 1: Implement `LocalWorker.from_paths()`**

Construct the existing `Runner` with the supplied package, binding, database, and namespace. Validate non-empty `worker_id`, positive `limit`, non-negative polling interval and stale-claim timeout.

- [x] **Step 2: Implement the single-active filesystem lock**

Open `<database>.worker.lock` and acquire `fcntl.LOCK_EX | LOCK_NB`. Raise `WorkerLockError` if another local worker owns it. Keep the file descriptor open until `close()`.

- [x] **Step 3: Implement `run_once()`**

Requeue stale claims, call `Runner.sweep(worker_id=..., limit=...)`, and return the bounded result list. The same completed wait must not be processed again.

- [x] **Step 4: Implement `run_forever()` with deterministic controls**

Run cycles until `stop_event` is set or `max_cycles` is reached. Sleep only between cycles, using `poll_interval`. `run_forever(max_cycles=1)` must be equivalent to one bounded cycle and must not sleep.

- [x] **Step 5: Run focused runtime tests**

Run:

```bash
uv run pytest tests/runtime/test_worker.py -q
```

Observed: `11 passed`.

### Task 4: Expose `mverse worker`

**Files:**
- Modify: `src/multiverse_workflow/cli/main.py`
- Modify: `tests/cli/test_runtime.py`
- Modify: `README.md`

- [x] **Step 1: Add CLI options**

Add `mverse worker <package> --binding <file> --db <file> --worker-id <id> --namespace <name> --poll-interval <seconds> --limit <n> --once --json`.

- [x] **Step 2: Map errors to existing local CLI exit semantics**

Use exit code `2` for invalid arguments/runtime construction failures, and code `5` only for service/network failures not used by this local Worker.

- [x] **Step 3: Emit machine-readable cycle results**

For `--once --json`, print:

```json
{"cycles": 1, "processed": [], "workerId": "local-worker"}
```

For non-JSON one-cycle mode, print one processed wait per line and a concise idle message.

- [x] **Step 4: Document the Worker boundary**

Document `mverse worker`, restart behavior, the single-active SQLite lock, and explicitly state that this milestone does not provide PostgreSQL, multi-worker, external outbox, or unknown external-effect reconciliation.

- [x] **Step 5: Run CLI tests**

Run:

```bash
uv run pytest tests/cli/test_runtime.py -q
```

Observed: CLI runtime tests pass as part of `11 passed` focused verification.

### Task 5: Verify, commit, and push the milestone

**Files:**
- Modify: `docs/superpowers/plans/2026-09-21-persistent-worker.md`

- [x] **Step 1: Run the focused and full Python verification**

```text
uv run pytest tests/runtime/test_worker.py tests/cli/test_runtime.py -q
11 passed

uv run pytest -q
169 passed

uv run ruff check src tests
All checks passed!

uv run mypy
Success: no issues found in 27 source files
```

- [x] **Step 2: Update this plan with completed steps and evidence**

Record only commands actually run and their observed results. Do not treat GitHub Actions or checklist state as test evidence.

- [x] **Step 3: Commit the milestone**

```bash
git add src/multiverse_workflow/runtime/worker.py \
  src/multiverse_workflow/runtime/ledger.py \
  src/multiverse_workflow/runtime/__init__.py \
  src/multiverse_workflow/cli/main.py \
  tests/runtime/test_worker.py \
  tests/cli/test_runtime.py \
  README.md \
  docs/superpowers/plans/2026-09-21-persistent-worker.md
git commit -m "feat: add persistent local worker"
```

Observed: commit `0b4ceda` (`feat: add persistent local worker`).

- [x] **Step 4: Push and verify the remote branch**

```bash
git push origin dev
git status --short --branch
git rev-parse HEAD
git ls-remote origin refs/heads/dev
```

The local and remote `dev` SHA must match. Existing untracked `inspector/pnpm-lock.yaml` and `inspector/pnpm-workspace.yaml` are not part of this commit and must remain untouched.

Observed: `git push origin dev` succeeded. Local and remote `dev` both point to
`0b4cedae3c8ae63d5ff4239f6391902fac60dd5c`. The two Inspector files remain
untracked and were not added.
