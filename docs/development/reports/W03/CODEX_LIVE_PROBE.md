# W03 Checkpoint: Real Codex Live Probe

Date: 2026-09-29
Base: `aaf2526`
Status: `live_probe_only`

## Commands

```bash
MULTIVERSE_RUN_CODEX_LIVE=1 \
  uv run --python 3.12 --locked pytest tests/integration/test_codex_live.py -q

MULTIVERSE_RUN_CODEX_LIVE=1 \
  uv run --python 3.12 --locked pytest tests/e2e/test_coding_delivery.py -q
```

## Result

- `tests/integration/test_codex_live.py`: `1 passed`
- `tests/e2e/test_coding_delivery.py`: `1 passed`
- Local Codex executable: `codex-cli 0.156.1`
- The probe produced structured JSON with a non-empty deliverable, an empty
  `artifact_refs` array, Runtime-shaped Artifact bytes, and `threadId` /
  `turnId` observations.

## Scope Boundary

These are authorized local live probes for the Codex bridge and producer
output contract. They do not prove the complete W03/W04 acceptance:

- no full Runtime multi-node Codex → verifier → HumanRequest run;
- no real approve/reject terminal Run evidence;
- no native interaction request/reply live evidence;
- no Worker stop/restart and Inspector reopen exactly-once evidence.

W03 and W04 remain `pending` in `docs/development/STATE.json`.
