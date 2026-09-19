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

This is a local single-process preview. HTTP Job, LangGraph persistence,
parallel/repeat execution, deployment/import, outbox/inbox recovery, and the
production HTTP API are not claimed as implemented yet.

## License

MIT
