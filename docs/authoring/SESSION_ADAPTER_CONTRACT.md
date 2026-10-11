# Native Session Adapter Contract

Executor adapters are registered by capability; the Runtime does not infer
session support from an adapter name. An adapter that can persist or resume a
native conversation may include a `nativeSession` object in an execution
observation:

```json
{
  "nativeSession": {
    "providerId": "codex",
    "installationId": "workstation-codex",
    "storageId": "codex-home-hash",
    "nativeSessionId": "provider-native-id",
    "providerVersion": "0.156.1",
    "capabilities": {
      "resume": true,
      "fork": true
    },
    "capabilityEvidence": "protocol_declared_unverified",
    "source": "new"
  }
}
```

`providerId`, `installationId`, and `storageId` form part of the native-session
identity; a native ID alone is never treated as globally unique. `source` is
one of `new`, `resume`, `fork`, or `handoff`. `capabilityEvidence` is
`protocol_declared_unverified` or `live_verified`; protocol presence alone must
not be represented as live verification. The adapter must report only
capabilities it implements for its pinned version. One-shot calls should omit
`nativeSession`; an ephemeral conversation ID is not a resumable session.

The Runtime persists this observation into an `AgentSession` and
`NativeSessionBinding`, associates it with the current Run/Scope/Invocation,
and emits a `agent.session.bound` event. Other adapters (including Hermes, Pi,
or a DeepSeek Harness integration) can use the same observation contract
without adding provider-specific branches to Runner or Ledger.

This contract records identity and declared capabilities. It does not itself
prove that a provider can resume/fork a particular session; that guarantee must
be live-tested for the adapter version and storage identity before advertising
the capability as verified.
