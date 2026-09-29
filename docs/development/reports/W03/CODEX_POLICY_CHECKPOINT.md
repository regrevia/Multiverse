# W03 Checkpoint: Codex Policy and Cooperative Stop

Date: 2026-09-29
Base: `b352bd8`
Status: `checkpoint_only`

## Delivered

- Codex App Server JSON-RPC bridge with structured thread/turn observations.
- Runtime-owned Artifact registration for Codex deliverables.
- Explicit Codex `cwd`, `workspaceRoot`, and `homeDir` configuration.
- Unknown-result handling for transport loss; no automatic retry after an
  accepted-but-unconfirmed Codex turn.
- Cooperative `turn/interrupt` with confirmation through
  `turn/completed.status=interrupted`.
- Run and node deadline checks before dispatch.
- Deadline convergence for created, running, and unknown attempts.
- Optional node `policy` with budget, limits, stop triggers, and Guard refs.
- Preflight diagnostics for unsupported or unregistered policy capabilities.

## Evidence

- Targeted Python tests: `62 passed`.
- Ruff: passed.
- Independent reviewer: approved as a `cooperative-stop/deadline`
  checkpoint.
- One real single-node Codex App Server call succeeded on local
  `codex-cli 0.156.1`, producing structured JSON and an observation with
  `threadId` and `turnId`.

## Limitations

This checkpoint does not complete W03 or W04. The following remain open:

- Codex interaction persistence for approval and request-user-input requests.
- Guard registry and executable Guard decisions.
- Complete live W03 integration test and multi-node Runtime evidence.
- Human approve/reject end-to-end evidence using the real Codex path.
- Worker restart and Inspector reopen evidence for exactly-once progression.
- Full macOS verification of Linux-only Execution Host tests.

The repository `STATE.json` therefore keeps W03 and W04 as `pending`.
