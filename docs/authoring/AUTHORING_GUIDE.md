# Multiverse Authoring Kit

This guide is the offline authoring entry point for the current local preview.
The normative documents are:

1. `docs/spec/MULTIVERSE_SPEC.md`
2. `docs/spec/MULTIVERSE_APPEND_SPEC.md`
3. The JSON Schemas in `schemas/` and each package's `schemas/` directory

The supplement is additional specification content. It does not grant runtime,
approval, deployment, network, or latent permissions.

## Current Support

The checked-in preview currently supports:

- YAML/JSON package loading with strict JSON-compatible values
- `multiverse/v0.1` Workflow, WorkflowPackage, and BindingSet resources
- deterministic package validation and execution plans
- sequential `call`, `switch`, and `end` execution
- builtin local executors
- persistent SQLite runs, scopes, invocations, attempts, events, and human requests
- `review` human requests with version, subject, authorization, expiry, and idempotency checks
- `input` human requests with direct output-schema JSON submissions
- local file registration as immutable, digest-checked ArtifactRefs
- machine-readable `validate`, `run`, `inspect`, and `decide` commands
- machine-readable `artifact register` command

The preview does not claim support for HTTP Job execution, Local Process
registration, LangGraph persistence, parallel/repeat execution, deployment or
import, production HTTP APIs, remote Artifact upload/registration, UI forms, or
Latent Handoff.

## Authoring Loop

Use this order for a package change:

```text
read spec and schemas
  -> define call input/output contracts
  -> define explicit references and branches
  -> add a Binding example without secrets
  -> mverse validate
  -> run the local fixture
  -> inspect the pending human request
  -> submit the authorized decision
  -> report tested, unverified, and unsupported behavior
```

Validation is static. It must not invoke executors or perform business side
effects. A local run does invoke the configured builtin and human adapters.

## Minimal Commands

Validate a package and binding:

```bash
uv run mverse validate presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --json
```

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
local runtime with `EXECUTOR_UNSUPPORTED`; this is an explicit support boundary,
not a successful HTTP execution.
