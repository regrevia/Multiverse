# W04 Evidence: Current Inspector Runtime Reopen

Date: 2026-09-30
Runtime: local trusted service `http://127.0.0.1:8788`
Inspector: current Vite development build `http://127.0.0.1:4173`
Workflow: `delivery`
Run: `run_66907af31bb04a6f8d1bc5336f6c04a5`

## Runtime facts

- Run status: `succeeded`
- Current node: `complete`
- Final event sequence: `40`
- Producer Attempt: `attempt_da0d420abb4b4eb09518a1c2a25f531e`
- Verifier Attempt: `attempt_688219aa8099436bb8e829803072c499`
- Business HumanRequest: `human_c62358fae0944b23af9fd830e69e1a73`
- Human decision: `decision_9fe874bb205047239142771fe2f65583`
- Decision actor: `example-reviewer`
- Decision subjectDigest:
  `sha256:10287d8862362e2a264a9523b4d32eab14ebf48ab369d162a4d3bcea90a63bb1`
- Artifact: `artifact_cae139b9acd74e8ea0b540c62286d0a7`
- Artifact digest:
  `sha256:ab3a74696700c5b5b41dabe8a663f657d67cf454590cfebc95720e98c40edebe`

## Browser procedure

1. Started the Runtime service against a copy of the real completed Runtime
   database and Artifact directory, using current Runtime code.
2. Opened the current Inspector build and connected to Runtime, namespace
   `local`, and the Run above.
3. Confirmed the live projection showed `Runtime 实时连接`, `已完成`, the exact
   Run ID, event sequence `40`, the completed workflow, and the registered
   Codex Artifact. The detail pane identified the content as read-only facts
   imported from the local Runtime ledger.
4. Reloaded the same browser tab. Inspector reconnected using current-tab
   `sessionStorage` and rebuilt the same Run projection without falling back
   to demo data.

Screenshot: `docs/development/reports/W04/assets/inspector-runtime-reopen.png`
SHA256: `1d13505a0e46c8ea2b4cd0892778783312590f25dd77ffba29a26fa6e60b770c`

The screenshot contains no bearer token. The token was held only in the local
browser session and is intentionally not recorded in repository evidence.
