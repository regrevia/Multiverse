# P0 Protocol Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first usable Multiverse Workflow slice: a strict, deterministic `mverse validate <package>` command that validates the normative content-delivery package and rejects the P0 negative fixtures with stable diagnostics.

**Architecture:** A dependency-light Python package owns protocol parsing, typed resource models, semantic compilation, and the CLI. YAML and JSON are converted into one JSON-compatible data model, then validation runs in the specification order: parse, resource shape, files/references, control flow, data references, required features, and optional binding preflight. The compiler returns a serializable execution plan and diagnostics without importing runtime, LangGraph, API, or UI types.

**Tech Stack:** Python 3.12, uv, Pydantic 2, ruamel.yaml, jsonschema Draft 2020-12, Typer, pytest, Ruff, mypy

---

### Task 1: Bootstrap the Python distribution and quality gates

**Files:**
- Create: `pyproject.toml`
- Create: `src/multiverse_workflow/__init__.py`
- Create: `src/multiverse_workflow/cli/__init__.py`
- Create: `src/multiverse_workflow/cli/main.py`
- Create: `tests/test_cli_smoke.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing CLI smoke test**

```python
from typer.testing import CliRunner
from multiverse_workflow.cli.main import app


def test_cli_exposes_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
```

- [ ] **Step 2: Run the smoke test and verify import failure**

Run: `uv run pytest tests/test_cli_smoke.py -q`

Expected: FAIL because `multiverse_workflow.cli.main` does not exist.

- [ ] **Step 3: Add the package metadata, CLI entrypoint, and minimal version command**

Use `requires-python = ">=3.12"` and register:

```toml
[project.scripts]
mverse = "multiverse_workflow.cli.main:app"
```

The callback must print package version `0.1.0` for `--version`.

- [ ] **Step 4: Lock dependencies and run the quality baseline**

Run:

```bash
uv lock
uv run pytest tests/test_cli_smoke.py -q
uv run ruff check .
uv run mypy src
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore src tests/test_cli_smoke.py
git commit -m "build: bootstrap Multiverse Python package"
```

### Task 2: Implement strict document loading and diagnostics

**Files:**
- Create: `src/multiverse_workflow/protocol/__init__.py`
- Create: `src/multiverse_workflow/protocol/diagnostics.py`
- Create: `src/multiverse_workflow/protocol/loader.py`
- Create: `tests/protocol/test_loader.py`

- [ ] **Step 1: Write failing tests for duplicate YAML keys, aliases, custom tags, non-finite numbers, and safe integers**

Tests must assert stable diagnostic codes:

```python
assert error.code == "DUPLICATE_KEY"
assert error.pointer == "/metadata/name"
```

The loader must return ordinary JSON-compatible Python values only.

- [ ] **Step 2: Run tests and verify they fail because the loader is absent**

Run: `uv run pytest tests/protocol/test_loader.py -q`

Expected: FAIL on missing module or symbol.

- [ ] **Step 3: Implement strict YAML 1.2/JSON loading**

Reject aliases, merge keys, custom tags, implicit timestamps, NaN/Infinity, integers outside `[-(2^53-1), 2^53-1]`, and duplicate keys. Define a serializable `Diagnostic` with code, file, pointer, message, severity, and suggestion.

- [ ] **Step 4: Verify loader tests and static checks**

Run:

```bash
uv run pytest tests/protocol/test_loader.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/multiverse_workflow/protocol tests/protocol
git commit -m "feat: add strict protocol document loader"
```

### Task 3: Define protocol resources and executable schemas

**Files:**
- Create: `src/multiverse_workflow/protocol/models.py`
- Create: `schemas/value-expr.schema.json`
- Create: `schemas/predicate.schema.json`
- Create: `schemas/workflow-package.schema.json`
- Create: `schemas/workflow.schema.json`
- Create: `schemas/binding-set.schema.json`
- Create: `tests/protocol/test_models.py`
- Create: `tests/protocol/test_schemas.py`

- [ ] **Step 1: Write failing model and schema tests**

Cover `WorkflowPackage`, `Workflow`, and `BindingSet`; reject unknown fields; validate metadata names and SemVer; require switch default; constrain repeat to 1-20; constrain call retries to 1-3.

- [ ] **Step 2: Run tests and verify missing models/schemas fail**

Run: `uv run pytest tests/protocol/test_models.py tests/protocol/test_schemas.py -q`

Expected: FAIL because models and schemas are absent.

- [ ] **Step 3: Implement discriminated Pydantic models and JSON Schemas**

Use `extra="forbid"` throughout. Model the six node types (`call`, `switch`, `workflow`, `parallel`, `repeat`, `end`), the four ValueExpr forms, and Predicate comparison/composition forms. Keep all types free of Runtime and LangGraph imports.

- [ ] **Step 4: Verify models, schemas, formatting, and typing**

Run:

```bash
uv run pytest tests/protocol/test_models.py tests/protocol/test_schemas.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/multiverse_workflow/protocol schemas tests/protocol
git commit -m "feat: define Multiverse protocol resources"
```

### Task 4: Materialize the normative package and P0 negative fixtures

**Files:**
- Create: `presets/content-delivery/manifest.yaml`
- Create: `presets/content-delivery/workflows/delivery.yaml`
- Create: `presets/content-delivery/schemas/request.json`
- Create: `presets/content-delivery/schemas/deliverable.json`
- Create: `presets/content-delivery/schemas/verification.json`
- Create: `presets/content-delivery/schemas/review-input.json`
- Create: `presets/content-delivery/schemas/review-output.json`
- Create: `presets/content-delivery/schemas/final-output.json`
- Create: `presets/content-delivery/evals/cases.jsonl`
- Create: `presets/content-delivery/evals/suite.yaml`
- Create: `examples/bindings/content-local.yaml`
- Create: `examples/bindings/content-remote.yaml`
- Create: `tests/fixtures/invalid/*`
- Create: `tests/protocol/test_normative_examples.py`

- [ ] **Step 1: Write failing tests that require every Appendix A file**

Load every normative YAML/JSON/JSONL file and assert the top-level resources parse as their declared kinds.

- [ ] **Step 2: Run tests and verify missing fixtures fail**

Run: `uv run pytest tests/protocol/test_normative_examples.py -q`

Expected: FAIL because Appendix A files are absent.

- [ ] **Step 3: Copy Appendix A exactly into executable fixture files**

Do not introduce credentials or environment endpoints. Add named negative fixture packages for duplicate keys, dangling edges, same-level cycles, missing references, switch without default, repeat overflow, unknown required feature, unresolved slot, and package-local secret material.

- [ ] **Step 4: Verify all examples parse**

Run: `uv run pytest tests/protocol/test_normative_examples.py -q`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add presets examples tests/fixtures tests/protocol/test_normative_examples.py
git commit -m "test: add normative protocol fixtures"
```

### Task 5: Compile packages into deterministic execution plans

**Files:**
- Create: `src/multiverse_workflow/compiler/__init__.py`
- Create: `src/multiverse_workflow/compiler/digests.py`
- Create: `src/multiverse_workflow/compiler/graph.py`
- Create: `src/multiverse_workflow/compiler/references.py`
- Create: `src/multiverse_workflow/compiler/compiler.py`
- Create: `tests/compiler/test_compile_package.py`
- Create: `tests/compiler/test_negative_packages.py`

- [ ] **Step 1: Write failing compiler tests**

The legal package must compile to a JSON-serializable plan containing explicit defaults, stable edges, source mappings, schema digests, required features, package digest, binding digest, and compiled plan digest. Each P0 negative fixture must fail with a stable code and source pointer.

- [ ] **Step 2: Run tests and verify compiler symbols are missing**

Run: `uv run pytest tests/compiler -q`

Expected: FAIL because `compile_package` does not exist.

- [ ] **Step 3: Implement deterministic compilation**

Implement local-only path resolution, Draft 2020-12 schema validation, required-feature checks, manifest/workflow linking, reachability, dangling-edge detection, same-level cycle detection, terminal path checks, ValueExpr root/pointer validation, slot resolution, secret-file scanning, canonical JSON hashing, and a serializable `ExecutionPlan`.

- [ ] **Step 4: Verify compiler and complete test suite**

Run:

```bash
uv run pytest tests/compiler -q
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/multiverse_workflow/compiler tests/compiler
git commit -m "feat: compile workflow packages into execution plans"
```

### Task 6: Expose validation through the CLI

**Files:**
- Modify: `src/multiverse_workflow/cli/main.py`
- Create: `tests/cli/test_validate.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI acceptance tests**

Assert:

```bash
mverse validate presets/content-delivery --binding examples/bindings/content-local.yaml --json
```

returns exit code 0 and a plan digest, while an invalid fixture returns exit code 2 and structured diagnostics on stdout in JSON mode.

- [ ] **Step 2: Run tests and verify the command is missing**

Run: `uv run pytest tests/cli/test_validate.py -q`

Expected: FAIL because `validate` is not registered.

- [ ] **Step 3: Implement the command and document the usable workflow**

Support package directory, optional binding file, repeated `--feature`, and `--json`. Human output must show pass/fail, package digest, workflow IDs, and source-located diagnostics. Validation must not invoke executors or perform business side effects.

- [ ] **Step 4: Run acceptance and full verification**

Run:

```bash
uv run mverse validate presets/content-delivery --binding examples/bindings/content-local.yaml --json
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Expected: valid package exits 0; all automated checks pass.

- [ ] **Step 5: Commit**

```bash
git add src/multiverse_workflow/cli tests/cli README.md
git commit -m "feat: expose protocol validation CLI"
```

