# HTTP Job Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable a real standards-shaped `http_job` execution path in the local preview with durable submission intent, stable dispatch identity, polling, and restart-safe continuation.

**Architecture:** Add a small synchronous HTTP Job client implementing the frozen `/v1/descriptor`, `/v1/executions`, lookup, observe, cancel, and artifact paths. Persist submit intent in the existing SQLite Ledger as an outbox row keyed by Attempt dispatch identity; persist observation waits keyed by Attempt. The single local Worker performs submit/observe and re-enters the existing Runner continuation only after a final observation is validated. Transport uncertainty remains unknown and is never converted into a fresh business submission.

**Tech Stack:** Python 3.12 standard-library `urllib`, SQLite, existing Runner/Worker/Ledger, pytest, Ruff, mypy.

---

### Task 1: Freeze the HTTP Job client contract with tests

**Files:**
- Create: `src/multiverse_workflow/runtime/http_job.py`
- Create: `tests/runtime/test_http_job.py`

- [x] **Step 1: Write tests for descriptor, submit, lookup, observe, and duplicate submit**

Use a local `ThreadingHTTPServer` fixture. Assert the request contains the stable `dispatchKey`, `effectKey`, input digest, schema digests, and context. Assert duplicate submit returns the same `executionRef` and a transport failure raises an explicit unknown-result exception.

- [x] **Step 2: Run the new tests and verify the intended RED failure**

Run `uv run pytest tests/runtime/test_http_job.py -q`. It must fail because the HTTP client module does not yet exist.

- [x] **Step 3: Implement the minimal client**

Use `urllib.request` with configured timeout, explicit JSON parsing, TLS-preserving URL handling, bounded response bytes, and typed protocol errors. Do not retry a submit after an unknown response. Expose `submit`, `lookup`, `observe`, `cancel`, and `fetch_artifacts`.

- [x] **Step 4: Run the client tests**

Run `uv run pytest tests/runtime/test_http_job.py -q` and confirm all protocol tests pass.

### Task 2: Add durable outbox and external observation waits

**Files:**
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Test: `tests/runtime/test_ledger.py`

- [x] **Step 1: Add failing Ledger tests**

Cover unique submit outbox rows by `submit:<attempt-id>`, durable status transitions, stable payload digest, one `external-observe:<attempt-id>` wait, and rescheduling a claimed wait after a non-final observation.

- [x] **Step 2: Add the SQLite outbox table and migrations**

Persist action key, Attempt identity, action, payload JSON/digest, status, external reference, attempt count, next time, and last error. Preserve compatibility with existing databases through additive initialization.

- [x] **Step 3: Add atomic Ledger helpers**

Implement ensure/complete/mark-unknown outbox operations, attach an external reference to an Attempt, ensure an external wait, reschedule a claimed wait, and keep unique keys enforced by SQLite.

- [x] **Step 4: Run Ledger tests**

Run `uv run pytest tests/runtime/test_ledger.py -q`.

### Task 3: Connect HTTP Job submit and observe to Runner/Worker

**Files:**
- Modify: `src/multiverse_workflow/runtime/runner.py`
- Modify: `src/multiverse_workflow/runtime/registry.py`
- Create: `tests/runtime/test_http_job_runtime.py`

- [x] **Step 1: Add an integration test with a real local HTTP Job server**

Use a binding with `adapter: http_job` and a test registry descriptor marked installed, available, verified, durable, and recoverable. Assert `Runner.start()` persists one submit outbox and an observation wait without finishing the Run. Polling a final valid observation finishes the same Attempt and advances the frozen graph without creating a second Attempt.

- [x] **Step 2: Add submit request construction and persistence**

Build the normative ExecutionRequest from frozen Run/Scope/Invocation/Attempt identities and schema digests. Persist the submit intent before the network call. On success persist `externalRef` and schedule observation. On transport uncertainty mark the Attempt unknown and schedule lookup; never auto-submit a different business action.

- [x] **Step 3: Add observation handling**

Worker claims external observation waits, validates monotonic/final status and output schema, reschedules non-final observations, and only then finishes Attempt/Invocation and re-enters `_drive`. Final failure uses existing retry/onError rules; protocol violations block the Run with audit evidence.

- [x] **Step 4: Run integration tests and restart recovery tests**

Run `uv run pytest tests/runtime/test_http_job.py tests/runtime/test_http_job_runtime.py tests/runtime/test_ledger.py tests/runtime/test_worker.py -q`.

### Task 4: Document the preview boundary and verify

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-09-21-http-job-runtime.md`

- [x] **Step 1: Document local HTTP Job setup**

Document the required `baseUrl`, standard endpoint behavior, Worker polling, stable deduplication, and the distinction between accepted, running, final, and unknown states.

- [x] **Step 2: Record unsupported boundaries**

Explicitly keep PostgreSQL, multiple active Workers, remote Connector pairing, production secret providers, and arbitrary third-party APIs without the standard Bridge contract outside this milestone.

- [x] **Step 3: Run complete verification**

```bash
uv run pytest tests/runtime/test_http_job.py tests/runtime/test_http_job_runtime.py tests/runtime/test_ledger.py tests/runtime/test_runner.py tests/runtime/test_worker.py -q
uv run pytest -q
uv run ruff check src tests
uv run mypy
git diff --check
```

### Task 5: Commit and push the milestone

```bash
git add src tests README.md docs/superpowers/plans/2026-09-21-http-job-runtime.md
git commit -m "feat: add durable http job runtime"
git push origin dev
git rev-parse HEAD
git ls-remote origin refs/heads/dev
git status --short --branch
```

Do not add `inspector/pnpm-lock.yaml` or `inspector/pnpm-workspace.yaml`.
