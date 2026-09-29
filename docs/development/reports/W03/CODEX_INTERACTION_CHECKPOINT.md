# W03 Checkpoint: Codex Interaction Persistence

Date: 2026-09-29
Base: `7ca0d45`
Status: `checkpoint_only`

## Delivered

- Persisted Codex native server requests as versioned Runtime interactions.
- Supported approval and request-user-input response shapes.
- Added authorized-subject, expected-version, expiry, and actor-scoped
  idempotency checks.
- Added Runtime API list/get/respond endpoints with namespace checks.
- Added same-connection JSON-RPC response delivery and explicit
  `deliveryStatus` / `invalidReason` projection fields.
- Added Worker restart recovery for pending and not-confirmed native
  interactions, including reconciliation waits.
- Added cross-entity Run/Scope/Invocation/Attempt integrity checks.
- Added migration fields for response digest, invalid reason, and delivery
  status; legacy interaction idempotency keys are migrated to
  `namespace:actor:key`.

## Evidence

- Targeted interaction/API/Ledger/Worker tests: `125 passed` in the affected
  suite before the final projection assertion, followed by the final
  interaction/API subset at `25 passed`.
- Ruff: passed.
- Independent reviewer: approved this interaction persistence checkpoint.
- Real native approval round-trip:
  `MULTIVERSE_RUN_CODEX_INTERACTION_LIVE=1`
  `tests/e2e/test_coding_delivery.py::test_real_codex_native_approval_is_persisted_replied_and_resumed`
  passed in 9.50s with Run
  `run_e5747022db2c4bedb4a036fc42896a84` and Interaction
  `interaction_916fd025303b4034af88701f63609bef`.
- The live round-trip used Codex `approvalPolicy=untrusted` and
  `sandboxMode=workspace-write`, persisted a real command approval request,
  accepted the authorized Runtime response, observed `deliveryStatus=sent`,
  verified the file write, and completed the separate business HumanRequest.

## Limitations

This checkpoint does not complete W03 or W04. Remaining work includes:

- Full Codex native interaction compatibility for handshake-time requests
  that do not yet carry thread/turn identity.
- Complete handshake-time interaction compatibility when native request
  payloads do not yet carry thread/turn identity.
- Codex → verifier → authorized human decision → terminal Run evidence.
- Worker stop/restart and Inspector reopen evidence for exactly-once
  progression.
- General multi-principal authentication beyond the local configured
  principal.

The repository `STATE.json` keeps W03 and W04 as `pending`.
