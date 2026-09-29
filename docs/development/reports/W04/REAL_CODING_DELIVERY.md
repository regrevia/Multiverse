# W04 Evidence: Real Codex Coding Delivery

Date: 2026-09-29
Environment: local trusted development profile, macOS, `codex-cli 0.156.1`

## Execution

The run used a temporary operator catalog and Binding:

```text
Codex producer
  -> deterministic critic
  -> builtin contract verifier
  -> HumanRequest
  -> authorized example-reviewer approve
  -> succeeded end
```

Run ID:

```text
run_c29c8c04b37a41268b1002b2f0f69111
```

Final status: `succeeded`.

## Evidence

- Producer Attempt: `succeeded`.
- Producer Runtime-owned Artifact:
  `artifact_2f5ea43379d4421d9463408014254541`.
- Artifact media type: `text/markdown`.
- Artifact size: 133 bytes.
- Critic Attempt: `succeeded`.
- Program verifier output: `valid=true`, `findings=[]`.
- HumanRequest:
  `human_30d303dd42e34187b57a398688b7c7a1`.
- Human decision: `approve`.
- Decision actor: `example-reviewer`.
- Human decision subject digest matched the persisted request.
- Final Run output contains the producer ArtifactRef, critic output, and
  approved review decision.
- Runtime event sequence contains:
  `agent.model.completed`, `artifact.created`, verifier success,
  `human.created`, `human.decided`, and final `run.updated` with
  `status=succeeded`.

## Restart Evidence

The live e2e suite also closes and reopens the same SQLite Runtime before the
HumanRequest decision. After reopening:

- the pending HumanRequest is recovered;
- the authorized approval resumes the same Run;
- Attempt count does not increase;
- Artifact count does not increase;
- replaying the same decision idempotency key does not advance the Run again.

Reproduction command:

```bash
MULTIVERSE_RUN_CODEX_LIVE=1 \
  uv run --python 3.12 --locked pytest \
  tests/e2e/test_coding_delivery.py::test_real_coding_delivery_survives_runtime_restart_before_approval \
  -q -s
```

The verified run printed `restart_e2e_run_id` and completed with `1 passed`.
The test asserts the original HumanRequest ID is recovered exactly, rather
than selecting a newly created pending request.

Verified restart Run ID:

```text
run_fdfc1cb3437e450ab1e97ab62d220fd0
```

The live e2e suite also verified a Worker restart before approval:

```bash
MULTIVERSE_RUN_CODEX_LIVE=1 \
  uv run --python 3.12 --locked pytest \
  tests/e2e/test_coding_delivery.py::test_real_coding_delivery_survives_worker_restart_before_approval \
  -q -s
```

Result: `1 passed in 12.31s`. The test printed
`worker_restart_e2e_run_id=run_c012735a807d485389c30b316ecd1db5`,
recovers the same HumanRequest after `LocalWorker.run_once()` and verifies
that approval does not create another Attempt or Artifact.

## Boundary

This is a real local coding-delivery evidence record, not a claim that all W03
or W04 acceptance is complete. Remaining gates include:

- full Codex native interaction live evidence;
- Worker stop/restart and Inspector reopen exactly-once evidence;
- complete W03 interaction and execution-host acceptance matrix;
- repeatable clean-environment installation evidence.

`docs/development/STATE.json` remains authoritative and keeps W03/W04
pending until their complete package gates are satisfied.
