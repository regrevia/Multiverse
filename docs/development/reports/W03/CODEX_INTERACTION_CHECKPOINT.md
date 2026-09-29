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
- A repeatable native approval e2e now covers the complete server-request path:
  ```bash
  MULTIVERSE_RUN_CODEX_INTERACTION_LIVE=1 \
    uv run --python 3.12 --locked pytest \
    tests/e2e/test_coding_delivery.py::test_real_codex_native_approval_is_persisted_replied_and_resumed \
    -q -s
  ```
  Latest verified run: `run_c441eb69101542d28d9626b3dd6d4b95`,
  Interaction `interaction_8649716f5e954cb1995056b36abfbec3`,
  `1 passed in 11.81s`. Ledger shows four successful Attempts,
  Interaction `replied/sent` by `example-reviewer`, and the business
  HumanRequest decided. The temporary workspace file contained
  `authorized write completed`.
- The same native-approval live test was re-run against the current test
  snapshot and passed in `10.96s` with Run
  `run_0219fd2ac0634215b07c9160969414aa` and Interaction
  `interaction_1e3d426f885241f58c8266b236ecdb2b`.

## Limitations

This checkpoint does not complete W03 or W04. Remaining work includes:

- Full Codex native interaction compatibility for handshake-time requests
  that do not yet carry thread/turn identity.
- Codex → verifier → authorized human decision → terminal Run evidence.
- Worker stop/restart and Inspector reopen evidence for exactly-once
  progression.
- General multi-principal authentication beyond the local configured
  principal.

Live interaction generation depends on the model choosing to invoke a tool.
The live e2e fails closed if Codex does not emit the expected native approval;
deterministic protocol fixtures cover the response/state machine independently.

The repository `STATE.json` keeps W03 and W04 as `pending`.
