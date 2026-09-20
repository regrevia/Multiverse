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
recovery, the production HTTP API, and Latent Handoff are not claimed as
implemented yet.

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

These controls are limited to the local SQLite preview. They do not yet provide
durable command receipts, external execution cancellation, worker recovery, or
reconciliation of an active external Attempt.

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
