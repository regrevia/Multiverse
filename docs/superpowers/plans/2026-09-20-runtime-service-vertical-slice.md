# Runtime Service Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the existing durable local Runtime through a service process so an external Agent or host can start, monitor, control, and complete a real human-in-the-loop workflow without owning workflow state.

**Architecture:** Keep `Ledger` and `Runner` as the only Runtime authority. Add a small Application Service that resolves an immutable deployment configuration and maps stable commands and queries to JSON-safe records. Add FastAPI routes for health, Run queries, graph/events, controls, human requests, durable command receipts, decisions, and SSE replay; the first service profile is explicitly local SQLite/single process and uses a configured local bearer token. Do not introduce a second workflow engine, database model, or browser-owned state.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic 2, SQLite local ledger, pytest, Typer.

---

### Task 1: Lock the service contract and dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/multiverse_workflow/service/contracts.py`
- Create: `tests/service/test_contracts.py`

- [x] **Step 1: Add service dependencies**

Add `fastapi>=0.116,<1` and `uvicorn[standard]>=0.35,<1` to runtime dependencies. Add `httpx>=0.28,<1` to the development group for ASGI tests, then run `uv lock`.

- [x] **Step 2: Write failing contract tests**

Cover:

```python
def test_run_create_request_requires_deployment_fields() -> None:
    with pytest.raises(ValidationError):
        RunCreateRequest.model_validate({"input": {"goal": "ship"}})

def test_command_receipt_is_pending_until_runtime_processes_it() -> None:
    receipt = CommandReceipt(
        request_id="request_1",
        status="accepted",
        resource_id="run_1",
        operation="run.create",
    )
    assert receipt.model_dump()["status"] == "accepted"
```

- [x] **Step 3: Define minimal typed DTOs**

`contracts.py` must define `RunCreateRequest`, `RunControlRequest`, `HumanDecisionRequest`, `CommandReceipt`, `ErrorBody`, `ErrorResponse`, and `RunSummary`. Use opaque string IDs, structured JSON values, explicit `expectedVersion`, and no secrets. `RunCreateRequest` accepts `deploymentId`, `workflowId`, `input`, and optional `externalRefs`; package and Binding paths are resolved by the configured deployment.

- [x] **Step 4: Run the focused test and confirm the initial failure**

Run:

```bash
uv run pytest tests/service/test_contracts.py -q
```

Expected: collection fails until the service package and models exist.

- [x] **Step 5: Implement the contract models and rerun**

Use Pydantic validation for non-empty paths, reasons, and IDs. Return JSON-safe aliases matching the service contract. The focused test must pass.

- [x] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/multiverse_workflow/service tests/service/test_contracts.py
git commit -m "feat: define runtime service contracts"
```

### Task 2: Add the Application Service facade

**Files:**
- Create: `src/multiverse_workflow/service/application.py`
- Create: `src/multiverse_workflow/service/errors.py`
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Create: `tests/service/test_application.py`

- [x] **Step 1: Write failing application tests**

Create a local content-delivery Run through the facade and assert that the Run is persisted, the returned record has a stable ID/version, and repeated `create_run` calls with the same idempotency key return the same Run. Add a stale-version pause test that raises `STATE_CONFLICT`.

- [x] **Step 2: Add event cursor queries**

Add `Ledger.list_events_after(run_id, after_seq, limit)` and `Ledger.get_event_cursor(run_id)` without changing existing event semantics. Enforce positive limits and return events ordered by `seq`.

- [x] **Step 3: Implement `RuntimeApplication`**

The facade must:

```python
class RuntimeApplication:
    def create_run(self, request: RunCreateRequest, *, idempotency_key: str) -> CommandReceipt: ...
    def get_run(self, namespace: str, run_id: str) -> dict[str, Any]: ...
    def get_graph(self, namespace: str, run_id: str) -> dict[str, Any]: ...
    def list_events(self, namespace: str, run_id: str, after: int, limit: int) -> list[dict[str, Any]]: ...
    def control_run(..., operation: Literal["pause", "resume", "cancel"]) -> CommandReceipt: ...
    def list_human_requests(...): ...
    def decide_human_request(..., idempotency_key: str) -> CommandReceipt: ...
```

It must cache no mutable Run authority, reject namespace mismatches, convert `LedgerConflict` to stable service errors, and use the existing `Runner` for execution and human resumption. Local package and binding paths are explicit configuration on the application object, never accepted from arbitrary browser HTML.

- [x] **Step 4: Run focused service tests**

Run:

```bash
uv run pytest tests/service/test_application.py -q
```

- [x] **Step 5: Commit**

```bash
git add src/multiverse_workflow/service src/multiverse_workflow/runtime/ledger.py tests/service/test_application.py
git commit -m "feat: add runtime application facade"
```

### Task 3: Expose HTTP JSON endpoints and SSE replay

**Files:**
- Create: `src/multiverse_workflow/api/app.py`
- Create: `src/multiverse_workflow/api/dependencies.py`
- Create: `tests/api/test_app.py`

- [x] **Step 1: Write failing ASGI tests**

Test:

1. `GET /health/live` returns 200.
2. `GET /health/ready` reports the configured local data path.
3. `POST /api/v1/namespaces/local/runs` returns 202 and a command receipt.
4. `GET /api/v1/namespaces/local/runs/{id}` returns the persisted Run.
5. `GET /graph` and `/events?after=0` return the Runtime projection and ordered events.
6. A stale `expectedVersion` returns HTTP 409 with `STATE_CONFLICT`.
7. `/stream?after=0` emits SSE IDs equal to event sequence numbers.

- [x] **Step 2: Implement service dependencies**

Create one application instance per process from explicit `ServiceSettings` (`database_path`, package directory, binding path, deployment ID, namespace, bearer token, and subject). Do not instantiate a new ledger for every event or request. Keep the local profile single-process and document that it is not PostgreSQL service mode.

- [x] **Step 3: Implement routes**

Use `/api/v1/namespaces/{namespace}` and JSON error envelopes. Require `Idempotency-Key` for state-changing POST routes. Implement:

```text
GET  /health/live
GET  /health/ready
POST /api/v1/namespaces/{namespace}/runs
GET  /api/v1/namespaces/{namespace}/runs/{run_id}
GET  /api/v1/namespaces/{namespace}/runs/{run_id}/graph
GET  /api/v1/namespaces/{namespace}/runs/{run_id}/events
GET  /api/v1/namespaces/{namespace}/runs/{run_id}/stream
POST /api/v1/namespaces/{namespace}/runs/{run_id}:pause
POST /api/v1/namespaces/{namespace}/runs/{run_id}:resume
POST /api/v1/namespaces/{namespace}/runs/{run_id}:cancel
GET  /api/v1/namespaces/{namespace}/human-requests
POST /api/v1/namespaces/{namespace}/human-requests/{request_id}/decisions
GET  /api/v1/commands/{command_id}
```

SSE must replay persisted events from `after` before polling for new events, use `seq` as `id`, and stop after an idle keepalive interval in tests. It must never mutate Runtime state.

- [x] **Step 4: Run API tests**

Run:

```bash
uv run pytest tests/api/test_app.py -q
```

- [x] **Step 5: Commit**

```bash
git add src/multiverse_workflow/api tests/api/test_app.py
git commit -m "feat: expose runtime HTTP and SSE APIs"
```

### Task 4: Add `mverse serve` and an end-to-end service fixture

**Files:**
- Modify: `src/multiverse_workflow/cli/main.py`
- Modify: `README.md`
- Modify: `docs/authoring/AUTHORING_GUIDE.md`
- Create: `tests/e2e/test_service_workflow.py`

- [x] **Step 1: Write the CLI and end-to-end acceptance test**

Start the ASGI app through its factory with the content-delivery local binding, create a Run over HTTP, observe `waiting`, submit the HumanRequest decision over HTTP, and assert the same Run reaches `succeeded` with an Artifact. Include a second assertion that closing the client between create and decide does not cancel the Run.

- [x] **Step 2: Add `mverse serve`**

Expose `mverse serve --db --package --binding --host --port` and call `uvicorn.run` with the configured application factory. `mverse serve --help` must not require a running database or execute a workflow.

- [x] **Step 3: Document the online monitoring loop and honest limits**

Document the local service command, API/SSE usage, HumanRequest flow, durable command receipts, and that this milestone is a local SQLite single-process preview. Do not claim PostgreSQL, multi-worker scheduling, Connector, or production isolation until separately verified.

- [x] **Step 4: Run the end-to-end test and all existing tests**

Run:

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy
git diff --check
```

- [x] **Step 5: Commit and push the milestone**

```bash
git add README.md docs/authoring/AUTHORING_GUIDE.md docs/superpowers/plans/2026-09-20-runtime-service-vertical-slice.md src tests pyproject.toml uv.lock
git commit -m "feat: add local runtime service vertical slice"
git push origin dev
```

### Explicitly deferred after this milestone

PostgreSQL repositories, multi-worker single-active locking, production authentication/IAM, remote Connector, external platform adapters, Feishu, Runnable Bundle installation, full React HTTP/SSE data client, and offline packaging remain separate milestones. Durable local command receipts are implemented, but external Attempt recovery and reconciliation remain separate milestones.
