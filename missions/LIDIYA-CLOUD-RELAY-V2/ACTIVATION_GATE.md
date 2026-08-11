# Cloud Autonomy Activation Gate

The relay state machine is active in development, but rapid unattended AI-to-AI execution is **not considered production-active** until these gates are satisfied.

## Gate A — Durable state proof

- [x] Dedicated branch exists: `lidiya-cloud-relay-v2`
- [x] Mission state exists
- [x] Packet hashing/dedup logic exists
- [x] Lease/reclaim logic exists
- [x] Coordinator / Builder / Verifier contracts exist
- [x] State unit tests exist
- [ ] GitHub Actions state tests independently pass in cloud runner
- [ ] `LCR-ROUNDTRIP-0001` completes A → B → C → A without a second human message

## Gate B — Agent engine authentication

Preferred initial engine: **Gemini**, with the work-machine agent named `雪璃` acting only as an edge starter/engine identity.

Preferred hardened implementation: GitHub Agentic Workflows (`gh-aw`) with `engine: gemini`.

One of the following must be configured outside source control:

- repository Actions secret `GEMINI_API_KEY`, or
- Google Workload Identity Federation for keyless auth.

Never commit an API key, OAuth token, cookie, browser session, or credential into this repository.

## Gate C — Default-branch launcher

GitHub `workflow_dispatch` orchestration requires the dispatchable workflow to exist on the repository default branch. Therefore:

1. Build/test all relay logic on `lidiya-cloud-relay-v2`.
2. Review the tiny launcher separately.
3. Promote only the minimal hardened launcher / compiled agentic workflows to `main` through review.
4. Launcher must target candidate branches, never grant autonomous merge-to-main authority.

## Gate D — Write boundaries

Cloud agents must obey:

- `main`: no autonomous merge
- candidate mission branches: scoped writes only
- identity/personality/governance: read-only to relay workers
- secrets: inaccessible to the model runtime except through provider-safe auth mechanisms
- safe outputs / protected files: enabled for code-changing agentic workflows
- reality evidence: tests/builds/hashes required before PASS

## Gate E — Metabolic closure

Before the relay opens the next mission automatically:

- stable/candidate disposition recorded
- evidence retained
- lesson retained
- rollback anchor recorded/tested as required
- scratch/debug/intermediate waste classified
- no orphan lease or unconsumed packet remains

## Transitional controller

Until the rapid GitHub-native agent chain is activated, a cloud scheduler may advance one safe, minimum verifiable relay cycle at a time from durable state. It must stop at `HUMAN_GATE` rather than invent credentials, broaden permissions, or bypass irreversible decisions.

This transition layer is continuity support, not a substitute for the final GitHub-native cloud relay.
