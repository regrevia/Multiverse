# Multiverse

Multiverse is an open-source project.

## Branches

- `dev`: default branch for development and testing
- `main`: release branch

## Local Runtime Preview

The current development slice supports the deterministic `content-delivery`
preset with the local SQLite runtime:

```bash
uv run mverse validate presets/content-delivery \
  --binding examples/bindings/content-local.yaml

printf '{"goal":"ship the release"}' > /tmp/mverse-request.json
uv run mverse run presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --input /tmp/mverse-request.json \
  --db .multiverse/runtime.db \
  --json
```

The run persists through producer, verifier, switch routing, and a HumanRequest.
Inspect the pending request in SQLite, then submit the authorized decision:

```bash
uv run mverse inspect <run-id> --db .multiverse/runtime.db --json
uv run mverse decide <request-id> presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --db .multiverse/runtime.db \
  --choice approve \
  --subject-digest <subject-digest> \
  --expected-version 1 \
  --json
```

This is a local single-process preview. Bounded sequential `repeat` execution
is available for child workflows, but HTTP Job, LangGraph persistence, parallel
and general nested workflow execution, deployment/import, outbox/inbox
recovery, production hosting/IAM, and Latent Handoff are not claimed as
implemented yet.

### Local Runtime Service

The service exposes the same SQLite Ledger and Runner through JSON and SSE. A
service request only commits a durable command and Run; the separate Worker
executes the workflow. This makes the local profile suitable for an Agent host
or an online monitoring prototype:

```bash
uv run mverse serve \
  --package presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --db .multiverse/runtime.db \
  --subject example-reviewer \
  --bearer-token dev-token \
  --host 127.0.0.1 \
  --port 8787
```

Create a real Run and keep the returned `resourceId`:

```bash
curl -X POST http://127.0.0.1:8787/api/v1/namespaces/local/runs \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dev-token' \
  -H 'Idempotency-Key: create-1' \
  -d '{
    "deploymentId": "deployment_local",
    "workflowId": "delivery",
    "input": {"goal": "write a release note"}
  }'
```

Start the local Worker in a second process so the queued Run can execute:

```bash
uv run mverse worker \
  --package presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --db .multiverse/runtime.db \
  --worker-id local-worker \
  --poll-interval 1
```

`POST /runs` and human decisions return after their durable command and
continuation intent are committed. Query the Run while the Worker is processing
it; the status may still be `queued`, `waiting`, or `running`. Disconnecting the
HTTP client does not cancel the Run, and replaying an `Idempotency-Key` returns
the original command and Run instead of starting a second execution.

Monitor the persisted audit stream and query pending human requests:

```bash
curl -H 'Authorization: Bearer dev-token' \
  http://127.0.0.1:8787/api/v1/namespaces/local/runs/<run-id>/stream
curl -H 'Authorization: Bearer dev-token' \
  'http://127.0.0.1:8787/api/v1/namespaces/local/human-requests?runId=<run-id>'
```

Submit the returned HumanRequest decision with its current `version` and
`subjectDigest`. All state-changing POST requests require an
`Idempotency-Key`; use the returned `requestId` with
`GET /api/v1/commands/{requestId}` to retrieve the durable command receipt
after reconnecting or restarting the service.

The current service profile uses local SQLite with one active Worker per
database. It does not claim PostgreSQL, multi-worker recovery, production IAM,
remote Connectors, or HTTP Artifact upload. The service does not keep workflow
state in the browser.

### Persistent Local Worker Sweep

Human decisions and retry backoffs are stored as durable waits. If the process
stops after a decision or before a retry is dispatched, start the same package
and binding again and sweep the due waits:

```bash
uv run mverse sweep presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --db .multiverse/runtime.db \
  --worker-id local-worker \
  --json
```

The sweep claims each wait once, rechecks the persisted Run, Scope and
Invocation state, and releases the wait if execution fails. It is a bounded
single-process recovery loop; it is not a distributed queue, an external
outbox, or proof that an unknown external side effect has stopped.

### Persistent Local Worker

For a continuously running local preview, use the persistent Worker. It owns
the SQLite database lock, recovers stale wait claims after a process restart,
and polls the same durable waits used by `sweep()`:

```bash
uv run mverse worker \
  --package presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --db .multiverse/runtime.db \
  --worker-id local-worker \
  --poll-interval 1
```

Use `--once --json` for a bounded health check or a test cycle:

```bash
uv run mverse worker presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --db .multiverse/runtime.db \
  --worker-id local-worker \
  --once --json
```

This is a local SQLite development preview with one active Worker per
database. It does not provide PostgreSQL coordination, multiple active
Workers, a distributed queue, an external outbox, or proof that an unknown
external side effect has stopped.

### Local Run Controls

Paused local runs stop new downstream dispatch. A valid HumanRequest decision
can still be recorded while paused, but only `resume` continues the persisted
flow. `cancel` invalidates pending local HumanRequests and prevents late
decisions from reviving the Run. `rerun` creates a new Run using the source
Run's frozen input and records its source; it does not copy an approval.

```bash
uv run mverse pause <run-id> \
  --db .multiverse/runtime.db \
  --expected-version <version> \
  --reason "hold for review" \
  --json

uv run mverse resume <run-id> \
  --package presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --db .multiverse/runtime.db \
  --expected-version <version> \
  --reason "continue" \
  --json

uv run mverse cancel <run-id> \
  --db .multiverse/runtime.db \
  --expected-version <version> \
  --reason "withdrawn" \
  --json
```

These controls are limited to the local SQLite preview. They do not provide
external execution cancellation. If an execution response is lost and its
persisted Attempt is `unknown`, an authorized operator can reconcile it through
the service boundary:

```bash
curl -X POST \
  http://127.0.0.1:8787/api/v1/namespaces/local/attempts/<attempt-id>:reconcile \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dev-token' \
  -H 'Idempotency-Key: reconcile-1' \
  -d '{
    "expectedVersion": 2,
    "conclusion": "confirmed_failed",
    "evidenceRefs": ["evidence://provider/failed"],
    "reason": "The provider confirmed the execution failed."
  }'
```

Only `confirmed_succeeded`, `confirmed_failed`, `confirmed_cancelled`, and
`confirmed_not_started` are accepted. A successful conclusion must include
output that passes the frozen node schema; the authenticated subject is
recorded and the request body cannot supply an actor.

### Inspector Snapshot

Export a read-only graph and audit snapshot for the Inspector or another local
viewer. The snapshot uses stable Scope and node identities and contains no
execution command or Artifact content endpoint.

```bash
uv run mverse inspect <run-id> \
  --db .multiverse/runtime.db \
  --graph \
  --json
```

在 `inspector` 中点击顶部的导入图标，选择上述 JSON 文件即可查看运行图。
导入内容是本地、只读、时间点快照；查看器不会通过文件导入触发运行、
暂停、恢复、取消或重新运行。
查看器中的节点和作用域可以在画布上拖动调整，仅影响当前浏览器视图；
点击画布工具栏的恢复布局图标可以回到自动布局。

### Trusted Local Ollama Agent Trial

The `content-ollama` binding runs a real local Ollama model through the
registered `builtin.ollama-deliverable.v1` executor in two distinct Binding
slots: a producer and a critic. The critic receives the fixed producer output
as structured input and produces a separate audit Artifact; it cannot approve
the workflow. The Runtime records each model call's name, token counts when
available, and output digest, then verifies and registers the two Runtime-owned
Artifact IDs before the program verifier and human review steps.

```bash
printf '{"goal":"write a concise release note"}' > /tmp/mverse-agent-request.json
uv run mverse run presets/content-delivery \
  --binding examples/bindings/content-ollama.yaml \
  --input /tmp/mverse-agent-request.json \
  --db .multiverse/ollama.db \
  --json
```

This trusted-local preview requires a running Ollama service and the configured
model (`qwen3.5:9b` in the example Binding). It is not a sandbox, does not
support model-call recovery or cancellation, and does not claim full offline
delivery support. Generated Artifact references are currently authorized only
within the same local Run and namespace; cross-subject Artifact ACLs are not
implemented.

### Manual Artifact Trial

The supplementary-spec trial preset lets a human complete a structured task
and submit a real local file as an `ArtifactRef`:

```bash
uv run mverse run presets/manual-input \
  --binding examples/bindings/manual-input-local.yaml \
  --input /tmp/mverse-request.json \
  --db .multiverse/manual.db \
  --json

uv run mverse artifact register <run-id> \
  --request-id <request-id> \
  --file ./release.md \
  --media-type text/markdown \
  --db .multiverse/manual.db \
  --json

uv run mverse decide <request-id> presets/manual-input \
  --binding examples/bindings/manual-input-local.yaml \
  --decision-file ./decision.json \
  --actor example-editor \
  --subject-digest <subject-digest> \
  --expected-version <version> \
  --db .multiverse/manual.db \
  --json
```

The decision file contains the output-schema object directly, for example
`{"artifact_refs":["artifact_..."],"change_summary":"Prepared the file."}`.

## License

MIT
