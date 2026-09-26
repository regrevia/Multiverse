# Multiverse

Multiverse is an **agent-authored, portable workflow runtime** for collaboration
between humans, agents, programs, and external services. Workflow packages define
business contracts; environment bindings select how and where work runs.

Agents are the primary workflow developers: files, schemas, capability discovery,
and machine-readable diagnostics form the authoring interface. The graphical
interface supports inspection, review, human tasks, and assisted editing.

Start with the [Agent authoring quickstart](docs/authoring/AGENT_QUICKSTART.md).
For continued development, follow the [ordered work packages and mandatory sub-agent review loop](工作包规划.md).
See the [competitive research and architecture rationale](docs/research/2026-09-26-portability-and-agent-authoring.md)
and the [normative specification](docs/spec/MULTIVERSE_SPEC.md#s30).

The implementation is a local development preview. Portable host embedding,
remote Connectors, Feishu channels, and Codex/Pi/Claude session management are
design targets, not completed integrations.

## Agent Authoring Preflight

```bash
uv run mverse capabilities --json
uv run mverse validate presets/content-delivery \
  --binding examples/bindings/content-local.yaml --json
uv run mverse preflight presets/content-delivery \
  --binding examples/bindings/content-local.yaml --json
```

Preflight adds read-only executor registry checks to static validation and
returns source-located diagnostics. It does not execute nodes or contact remote
services. Read `notChecked` before treating a result as evidence: permissions,
sandbox enforcement, credentials, executor configuration, and business quality
are not verified by this local check. Failed checks exit with code 2.

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

This is a local single-process preview. Bounded sequential `repeat`, nested
`workflow`, and static `parallel` with `join: all` are available as durable
child scopes. The standard HTTP Job path is available when the Binding points
at a trusted test or Bridge service; LangGraph persistence, deployment/import,
production hosting/IAM, and Latent Handoff remain outside this preview.

### Standard HTTP Job Binding

An HTTP Job Binding uses the standard `/v1` lifecycle and must be registered as
an installed, available, and verified executor. Its configuration supplies the
service URL and request timeout:

```yaml
slots:
  producer:
    adapter: http_job
    executorRef: example.remote-content.v1
    config:
      baseUrl: http://127.0.0.1:9000
      timeoutSeconds: 30
```

The service must implement `GET /v1/descriptor`, `POST /v1/executions`,
dispatch-key lookup, observation, cancel, and artifact metadata endpoints.
`POST /v1/executions` is a durable submission boundary: an accepted response
only gives an external reference, while `running` and terminal state come from
later observations. The local Worker polls the persisted observation wait and
only advances the graph after a final observation passes the frozen output
schema and Artifact checks.

The Runtime persists one submit intent per Attempt and keeps the same
`dispatchKey` across transport retries. A lost submit response becomes
`unknown`; the Worker first performs lookup and can only resume the original
execution when the service returns the matching reference. It never creates a
second business Attempt for that uncertainty. Observation revisions are
monotonic; a repeated revision with different content is a protocol violation
and blocks the Run with audit evidence. `failed` observations use the node's
existing retry and `onError` rules, while a final `unknown` observation remains
in reconciliation.

The HTTP Job preview requires one active local Worker per SQLite database:

```bash
uv run mverse worker \
  --package presets/content-delivery \
  --binding examples/bindings/content-remote.yaml \
  --db .multiverse/runtime.db \
  --worker-id http-worker \
  --poll-interval 1
```

PostgreSQL, multiple active Workers, production Secret Providers/IAM, remote
Connector pairing, and arbitrary third-party APIs without a standard Bridge
remain unsupported. A custom `ExecutorRegistry` is required for the current
development HTTP Job binding; the default local registry intentionally does
not trust an arbitrary URL as a production executor.

### Local Process Node

Scripts and executables can be nodes through the built-in JSON process adapter:

```yaml
slots:
  transform:
    adapter: local_process
    executorRef: local.process.v1
    config:
      command: [python, scripts/transform.py]
      timeoutSeconds: 30
```

The Worker sends the node input as JSON on stdin and expects one JSON value on
stdout. A non-zero exit, timeout, or invalid output follows the node's retry
and error policy. The command runs with the Worker user's permissions; use a
dedicated sandbox or service account for production workloads.

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

Attempt reconciliation follows the same two-step boundary. The reconcile
endpoint durably records the provider conclusion, evidence, and authenticated
actor, then returns a command receipt; it does not synchronously advance the
Invocation or downstream graph. The local Worker consumes the persisted
`attempt-reconcile:<attempt-id>` wait and applies the conclusion exactly once.
Query the Run again after a Worker cycle before treating the workflow as
failed, cancelled, or resumed. A cancelled Run can still have a reconciliation
wait while an in-flight unknown external action is being closed out.

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
Workers, a distributed queue, a remote Job or Connector lookup adapter, a
production outbox/inbox, or proof that an unknown external side effect has
stopped. The reconciliation endpoint stores real local evidence supplied by
the caller; it is not a substitute for a real provider lookup implementation.

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
