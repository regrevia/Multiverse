# Multiverse Authoring Kit

Agents are the primary workflow developers; graphical editing is auxiliary.
Start with [AGENT_QUICKSTART.md](AGENT_QUICKSTART.md) for the short operating loop.
This guide is the offline authoring reference for the current local preview.
The only normative document is `docs/spec/MULTIVERSE_SPEC.md`. The JSON
Schemas in `schemas/` and each package's `schemas/` directory are its
executable representations; they do not create a parallel specification.

## Current Support

The checked-in preview currently supports:

- YAML/JSON package loading with strict JSON-compatible values
- `multiverse/v0.1` Workflow, WorkflowPackage, and BindingSet resources
- deterministic package validation and execution plans
- sequential `call`, `switch`, and `end` execution
- bounded sequential `repeat` execution through separately persisted child scopes
- nested `workflow` execution through separately persisted child scopes
- static `parallel` execution with stable branch IDs, `join: all`, and bounded
  `maxConcurrency`
- builtin local executors
- trusted local JSON-in/JSON-out process execution (not a sandbox)
- read-only `preflight --json` for local registry status, config shapes, and source-located gaps
- persistent SQLite runs, scopes, invocations, attempts, events, and human requests
- `review` human requests with version, subject, authorization, expiry, and idempotency checks
- version-checked local pause, resume, cancel, and terminal-run rerun commands
- `input` human requests with direct output-schema JSON submissions
- local file registration as immutable, digest-checked ArtifactRefs
- machine-readable `validate`, `run`, `inspect`, and `decide` commands
- durable command receipts for service commands and idempotent retries
- version-checked Attempt reconciliation for persisted `unknown` results,
  including evidence, authenticated actor, and frozen output-schema validation
- machine-readable `artifact register` command
- read-only JSON Inspector snapshots with scopes, nodes, events, HumanRequests, and Artifacts
- local FastAPI JSON and SSE service over the same SQLite Runtime

The preview does not claim support for arbitrary executor plugin installation, LangGraph
persistence, deployment or import, production hosting/IAM, remote Artifact
upload/registration, UI forms, or Latent Handoff. The HTTP Job path is
available only through a verified development Binding and the local Worker;
it does not claim production Connector behavior. The HTTP/SSE service is a
local SQLite single-process profile; it does not provide PostgreSQL,
multi-worker scheduling, or confirmed cancellation of external Attempts.
Reconciliation is available only for an already persisted `unknown` Attempt
and does not prove that an external provider can be queried or cancelled.
Command receipts and local Run records survive application restart, while
active external execution recovery is not claimed. Inspector snapshots remain
local point-in-time DTOs;
the service API is a separate Runtime boundary and does not turn snapshots
into a browser-owned workflow engine.

## Authoring Loop

Use this order for a package change:

```text
read spec and schemas
  -> define call input/output contracts
  -> define explicit references and branches
  -> add a Binding example without secrets
  -> mverse validate
  -> mverse preflight --json (registry status and config shapes)
  -> run the local fixture
  -> inspect the pending human request
  -> submit the authorized decision
  -> report tested, unverified, and unsupported behavior
```

Validation is static. It must not invoke executors or perform business side
effects. A local run invokes the configured executors; process and HTTP bindings can have
real side effects. Preflight only reads package/Binding files and registered metadata;
it checks the configuration shapes supported by the registered backend and its
additional config Schema. It does not check live connectivity, credentials,
authorization, sandbox enforcement, human delivery, or business quality.
Only completion of every call configuration check adds `executor-config` to
`checked`; static validation failures, catalog revocation, and unresolved
slots/executors leave it in `notChecked`. Config diagnostics identify the
field with a JSON pointer and provide `expected` constraints and redacted `actual`
types, so authors can repair a Binding without disclosing its values.

## Minimal Commands

Validate a package and binding:

```bash
uv run mverse validate presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --json
```

List the local machine-readable capability catalog:

```bash
uv run mverse capabilities --json
uv run mverse capabilities --executor local.process.v1 --json
```

The catalog reports `declared`, `installed`, `available`, and `verified`
separately. In the current preview the builtin and human fixtures are
available; the example HTTP executor is declared for validation examples but
is not available for local execution.

Use an explicitly reviewed operator catalog when the default registrations do not
represent the execution environment:

```bash
uv run mverse capabilities --registry examples/executor-catalog --executor local.process.v1 --json
uv run mverse preflight presets/content-delivery \
  --binding examples/bindings/content-local.yaml --registry examples/executor-catalog --json
```

The [complete registration example](../../examples/executor-catalog/README.md)
documents manifest fields, Schema digests, config repair, and snapshot changes.
An explicit directory replaces all defaults, including builtin/human entries.
Its versioned `verificationEvidence` is an operator attestation; loading a catalog
does not run its claimed tests or grant trust to a package-provided directory.
The same `--registry` option is available for validate/run/serve/worker and the
sweep/resume/rerun/decide paths. Keep service and Worker on the same chosen catalog.

Start a local run:

```bash
printf '{"goal":"ship the release"}' > /tmp/mverse-request.json
uv run mverse run presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --input /tmp/mverse-request.json \
  --db .multiverse/runtime.db \
  --json
```

Inspect a persisted run:

```bash
uv run mverse inspect <run-id> \
  --db .multiverse/runtime.db \
  --json
```

Export its graph projection:

```bash
uv run mverse inspect <run-id> \
  --db .multiverse/runtime.db \
  --graph \
  --json
```

将命令输出保存为 JSON 后，在 `inspector` 顶部点击导入图标即可载入审计图。
导入只替换查看器的本地视图，不调用 Runtime 命令；内容代表导出时刻，
不会自动跟随运行变化，也不提供 HTTP、SSE、分页或授权能力。
画布节点和作用域支持本地拖动排布，排布不会写回 Runtime；恢复布局图标
会清除本次查看器会话中的坐标覆盖。

Submit a review decision:

```bash
uv run mverse decide <request-id> presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --db .multiverse/runtime.db \
  --choice approve \
  --subject-digest <subject-digest> \
  --expected-version <version> \
  --json
```

The `run` command exits with code `4` while a human request is pending.
`decide` resumes the same persisted run. Reusing the same idempotency key
returns the original result instead of replaying downstream nodes.

For an `input` request, first register a completed local file:

```bash
uv run mverse artifact register <run-id> \
  --request-id <request-id> \
  --file ./release.md \
  --media-type text/markdown \
  --db .multiverse/runtime.db \
  --json
```

Then submit a JSON file whose root value directly satisfies the node's
`outputSchema`:

```json
{
  "artifact_refs": ["artifact_..."],
  "change_summary": "Prepared the release document."
}
```

The registration command copies the file into the local Artifact store,
records a content digest, and does not complete the HumanRequest. The final
decision still checks request version, subject digest, actor authorization,
output Schema, Artifact existence, run ownership, and content digest.

## Service Monitoring Loop

Start the local service with the package and binding explicitly configured:

```bash
uv run mverse serve \
  --package presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --db .multiverse/runtime.db \
  --subject example-reviewer \
  --bearer-token dev-token \
  --port 8787
```

An external Agent or host then uses:

```text
POST /api/v1/namespaces/{namespace}/runs
GET  /api/v1/namespaces/{namespace}/runs/{runId}
GET  /api/v1/namespaces/{namespace}/runs/{runId}/graph
GET  /api/v1/namespaces/{namespace}/runs/{runId}/events?after=0
GET  /api/v1/namespaces/{namespace}/runs/{runId}/stream?after=0
GET  /api/v1/namespaces/{namespace}/human-requests?runId={runId}
POST /api/v1/namespaces/{namespace}/human-requests/{requestId}/decisions
POST /api/v1/namespaces/{namespace}/attempts/{attemptId}:reconcile
GET  /api/v1/commands/{requestId}
```

The SSE stream replays persisted events before polling and uses the Ledger
event `seq` as the SSE `id`. A disconnected client can reconnect from its last
sequence number; disconnecting does not cancel a Run. Every state-changing POST
requires an `Idempotency-Key`, while HumanRequest decisions additionally
require the persisted request version, subject digest, and authenticated
principal authorization. Attempt reconciliation additionally requires
`expectedVersion`, `evidenceRefs`, and `reason`; the request body never
supplies a namespace or actor.
Run creation uses `deploymentId`, `workflowId`, `input`, and optional
`externalRefs`; the server resolves package and Binding from the immutable
deployment configuration.

## Package Rules

- Keep credentials, private URLs, local paths, and environment grants in the
  Binding or secret provider, never in the portable package.
- Treat `executorRef` and capabilities as environment facts. Do not invent an
  executor ID that is not registered by the current implementation.
- Use explicit JSON Schema for every workflow and call input/output.
- Keep execution status, business output, and explanatory comments separate.
- Use structured switch predicates for business outcomes such as `valid=false`
  or `decision=reject`; do not turn them into transport failures.
- Human review requires an authorized subject, a current subject digest, and
  the expected request version.
- A valid JSON shape does not prove that an Artifact exists, that an external
  action happened, or that a human had the required identity.

## Capability Status Vocabulary

When reporting environment capabilities, use these separate states:

- `declared`: described by a package, descriptor, or document
- `installed`: present in the local environment
- `available`: currently usable under the active configuration
- `verified`: exercised by an appropriate test or authorized execution

Do not collapse a declaration or installation into a verified support claim.

## Delivery Report

Every authoring change should report:

- package and workflow versions
- changed files
- input/output contracts and branches
- Binding slots and required capabilities
- permissions and possible side effects
- commands and evidence actually run
- unverified or unsupported capabilities
- deployment or environment work still required

The current preview's main trial package is
`presets/content-delivery`. Its remote binding is intentionally rejected by the
default preflight because the HTTP executor is not installed/available/verified
and its illustrative config lacks `baseUrl`. A trusted registration and valid
HTTP Job configuration are required for execution; static validation alone does
not establish remote readiness.
