# Public Source Publication Boundary

Date: 2026-10-11

## Baseline and local-only commits

The publication candidate is based on the verified public `origin/dev` commit
`dc7b02e4c687081a67881e1c1f30d5b58b7e0c67`.

The former local `dev` tip had two commits not present on the public branch:

- `8d5247c`: local Multiverse development workflow package, local Bindings,
  launcher, and workflow-specific tests.
- `6aa677c`: mixed workflow changes and reusable Runtime/Inspector source.

Neither original commit is part of this publication candidate. Reusable
Runtime/Inspector changes from the mixed commit were re-applied as ordinary
source changes and independently tested. The workflow package, local Bindings,
absolute workspace configuration, launcher, and workflow-specific tests were
excluded.

## Included source changes

- Generic native-session observation contract for registered execution
  adapters; Runner does not branch on Codex, Claude, Pi, Hermes, or another
  provider name.
- Persist explicit native session identity and declared capabilities through
  the existing Ledger session tables.
- Expose pending Codex native interactions in Inspector with replies routed
  through the authenticated, versioned Runtime API.
- Allow explicitly configured Claude read-only tools for review adapters.

## Verification

- Full Python suite after publication-boundary review fixes: `658 passed, 59 skipped`.
- Inspector: `48 passed`; Vite build passed.
- Ruff and mypy passed.
- `git diff --check` passed.
- Review scope contained source and tests only; no `presets/multiverse-development`,
  local development Binding, local workflow launcher, database, or runtime log.

The prior local `dev` branch is preserved separately and is not pushed. This
report does not claim that the local workflow was removed from that local
branch.

## Review fixes included before publication

- Native Session binding write failures no longer leave a completed provider
  turn represented as a running Attempt.
- Explicit cross-Run resume reuses the same logical AgentSession, records a
  per-Run use, and requires matching Agent/Profile/Workspace/Policy revisions.
- A native Session turn lease serializes concurrent writers and carries a
  fencing token. Unknown provider outcomes retain the lease until explicit
  reconciliation.
- Claude one-shot calls omit ephemeral session IDs from durable observations.
- Resume/fork capabilities are stored separately from the capability map and
  marked `protocol_declared_unverified` until live verification exists.
- Legacy SQLite native-session uniqueness constraints migrate to active-only
  identity uniqueness while preserving superseded binding history.
- The lease has a per-execution owner token; repeat acquisition by the same
  durable Attempt from another process is rejected. A stale lease can only be
  reclaimed after its owner Attempt is terminal, or after explicit
  reconciliation releases the unknown Attempt's lease.
- Re-activating the same native identity creates a new binding-history row;
  superseded rows are retained while the active identity remains unique.
