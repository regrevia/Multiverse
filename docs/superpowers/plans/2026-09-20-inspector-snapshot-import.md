# Inspector Snapshot Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the React Inspector display a local `mverse inspect --graph --json` snapshot without giving the browser authority to change a Run.

**Architecture:** A UI mapper converts the framework-neutral runtime DTO into the existing `AuditGraph` display model. The Inspector accepts one local JSON file through a hidden file input, replaces only local view state, and shows a concise parse error when the file is not a valid snapshot. Demo data remains the empty-state preview.

**Tech Stack:** React 19, TypeScript, Vite, Vitest.

---

### Task 1: Lock runtime DTO mapping with failing tests

**Files:**
- Create: `inspector/src/graph/runtime.test.ts`
- Modify: `inspector/src/graph/model.ts`

- [x] **Step 1: Add a projection mapper test**

```ts
expect(mapRuntimeProjection(snapshot).runId).toBe("run_123");
expect(graph.nodes.find((node) => node.id === "scope_root:review")?.status).toBe("waiting");
expect(graph.groups[0]?.memberIds).toContain("scope_root:review");
```

- [x] **Step 2: Run the focused test**

Run:

```bash
npm run test:run -- src/graph/runtime.test.ts
```

Expected: FAIL because no mapper exists.

### Task 2: Map runtime facts into the display model

**Files:**
- Create: `inspector/src/graph/runtime.ts`
- Modify: `inspector/src/graph/model.ts`
- Test: `inspector/src/graph/runtime.test.ts`

- [x] **Step 1: Define the narrow imported DTO type**

Include the read-only fields emitted by `inspect --graph`: Run, scopes, nodes,
edges, events, HumanRequests, and Artifacts. Do not accept functions, HTML, or
arbitrary view coordinates from the file.

- [x] **Step 2: Produce stable UI nodes and scope groups**

Map runtime status to the existing view statuses, derive a concise node detail
from invocation/Attempt facts, attach Artifact and HumanRequest evidence, and
lay out nodes deterministically by scope/node order. Rejected/unrecognized
runtime status values map to `failed` rather than becoming implicit success.

- [x] **Step 3: Run the focused test**

Run:

```bash
npm run test:run -- src/graph/runtime.test.ts
```

Expected: PASS.

### Task 3: Add local snapshot import

**Files:**
- Modify: `inspector/src/App.tsx`
- Modify: `inspector/src/styles.css`
- Test: `inspector/src/graph/runtime.test.ts`

- [x] **Step 1: Add a hidden JSON file input**

The top bar uses an icon button with a tooltip and a native file picker. It
reads only one selected JSON file, calls the mapper, sets local `graph` state,
and resets the selected node to a valid imported node.

- [x] **Step 2: Show import state in the existing compact top bar**

Show a short Chinese source label and a local parse error without turning the
screen into a setup page. Importing never calls a Runtime command.

- [x] **Step 3: Build and test**

Run:

```bash
npm run test:run
npm run build
```

Expected: PASS.

### Task 4: Verify and publish the milestone

**Files:**
- Modify: `README.md`
- Modify: `docs/authoring/AUTHORING_GUIDE.md`

- [x] **Step 1: Document the local import loop**

Show the `mverse inspect --graph --json` command and say that selecting the
result in the Inspector is read-only and point-in-time.

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
  docs/superpowers/plans/2026-09-20-inspector-snapshot-import.md \
  inspector/src/App.tsx inspector/src/styles.css \
  inspector/src/graph/model.ts inspector/src/graph/runtime.ts \
  inspector/src/graph/runtime.test.ts
git commit -m "feat: import runtime snapshots in inspector"
git push origin dev
```

### Task 5: Add local canvas layout controls

**Files:**
- Create: `inspector/src/graph/layout.ts`
- Create: `inspector/src/graph/layout.test.ts`
- Modify: `inspector/src/App.tsx`

- [x] **Step 1: Add a tested coordinate translation helper**

- [x] **Step 2: Let nodes and scopes move in the local Inspector view**

Dragging a scope moves its visible members by the same delta. These positions
are local view state and are discarded when a new snapshot is imported.

- [x] **Step 3: Add a reset-layout control and verify in a browser**

The reset control clears local coordinate overrides and restores the mapper's
deterministic layout.

- [x] **Step 4: Run focused frontend tests and build**
