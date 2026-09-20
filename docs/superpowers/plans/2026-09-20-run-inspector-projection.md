# Run Inspector Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export a stable, framework-neutral snapshot of a persisted Run for the React audit viewer and other read-only clients.

**Architecture:** Build the projection only from the frozen `plan_json` and the SQLite ledger. Scope, node, invocation, Attempt, event, HumanRequest, and Artifact identities remain explicit; the projection does not contain React Flow coordinates, execute commands, or mutate runtime records.

**Tech Stack:** Python 3.12, SQLite, Typer, pytest.

---

### Task 1: Lock the projection contract with failing tests

**Files:**
- Create: `tests/runtime/test_projection.py`
- Modify: `tests/cli/test_runtime.py`

- [x] **Step 1: Add a waiting-run projection test**

```python
def test_projection_exposes_frozen_graph_and_waiting_human_request(...):
    waiting = runner.start({"goal": "ship the release"})
    view = build_run_projection(runner.ledger, waiting["id"])

    assert view["run"]["status"] == "waiting"
    assert view["nodesById"]["<root-scope>:produce"]["invocation"]["status"] == "succeeded"
    assert view["nodesById"]["<root-scope>:review"]["invocation"]["status"] == "waiting"
    assert view["humanRequests"][0]["status"] == "pending"
```

- [x] **Step 2: Add a CLI JSON export test**

```python
result = CLI.invoke(app, ["inspect", run_id, "--db", str(database), "--graph", "--json"])
assert result.exit_code == 0
assert json.loads(result.stdout)["protocolVersion"] == "multiverse/v0.1"
```

- [x] **Step 3: Run focused tests**

Run:

```bash
uv run pytest -q tests/runtime/test_projection.py tests/cli/test_runtime.py -k "projection or graph"
```

Expected: FAIL because the projection module and `inspect --graph` do not exist.

### Task 2: Build the read-only projection

**Files:**
- Create: `src/multiverse_workflow/runtime/projection.py`
- Modify: `src/multiverse_workflow/runtime/ledger.py`
- Test: `tests/runtime/test_projection.py`

- [x] **Step 1: Add read-only ledger lists**

```python
def list_attempts(self, run_id: str) -> list[dict[str, Any]]: ...
def list_artifacts(self, run_id: str) -> list[dict[str, Any]]: ...
```

- [x] **Step 2: Map the frozen plan and ledger facts**

```python
def build_run_projection(ledger: Ledger, run_id: str) -> dict[str, Any]:
    ...
```

The returned object contains `protocolVersion`, a redacted Run summary, `scopes`,
stable `nodes` and `edges`, `events`, HumanRequest summaries, and Artifact
summaries. A node ID is `<scope_id>:<node_id>` so repeat iterations never
overwrite one another. Invocation and latest Attempt records are nested under
their node and raw input/output values remain out of the graph summary.

- [x] **Step 3: Run projection tests**

Run:

```bash
uv run pytest -q tests/runtime/test_projection.py
```

Expected: PASS.

### Task 3: Expose the projection through the existing CLI

**Files:**
- Modify: `src/multiverse_workflow/cli/main.py`
- Test: `tests/cli/test_runtime.py`

- [x] **Step 1: Add `inspect --graph`**

`mverse inspect <run-id> --graph --json` returns the projection rather than the
raw Run row. `--graph` requires `--json` so the text CLI output remains a small
Run summary.

- [x] **Step 2: Run focused CLI tests**

Run:

```bash
uv run pytest -q tests/cli/test_runtime.py -k graph
```

Expected: PASS.

### Task 4: Verify and publish the milestone

**Files:**
- Modify: `README.md`
- Modify: `docs/authoring/AUTHORING_GUIDE.md`

- [x] **Step 1: Document the DTO boundary**

Describe the projection as a local read-only snapshot for the Inspector; do not
claim HTTP, SSE, pagination, authorization, or embedded SDK support.

- [x] **Step 2: Run full verification**

Run:

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy
git diff --check
(cd inspector && npm run test:run && npm run build)
```

Expected: all commands exit with status 0.

- [x] **Step 3: Commit and push**

```bash
git add README.md docs/authoring/AUTHORING_GUIDE.md \
  docs/superpowers/plans/2026-09-20-run-inspector-projection.md \
  src/multiverse_workflow/runtime/ledger.py \
  src/multiverse_workflow/runtime/projection.py \
  src/multiverse_workflow/cli/main.py \
  tests/runtime/test_projection.py \
  tests/cli/test_runtime.py
git commit -m "feat: export run inspector projection"
git push origin dev
```
