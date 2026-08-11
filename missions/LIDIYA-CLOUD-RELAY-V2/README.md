# LIDIYA CLOUD RELAY v2

Mission: `LCR-V2-ROUNDTRIP-0001`
Branch: `cloud-relay-v2`
Status: sandbox / development only

## Goal

Run a three-slot cloud relay that can continue development after one START signal without depending on a specific local PC or browser conversation history.

The three slots are roles, not trusted memory containers:

- `LCR-A` — Coordinator: owns mission state, chooses the next smallest verifiable step, and decides PROJECT_DONE.
- `LCR-B` — Builder: implements only the task packet from A and emits result + evidence. Builder never declares the mission complete.
- `LCR-C` — Verifier: independently checks B's evidence and emits PASS / FAIL / DEFER / NEEDS_BOXUAN_APPROVAL.

All slots must recover context from repository/Drive state. A browser window may disappear without becoming a loss of mission state.

## Sources of truth

1. Governance/personality/approved memory: Google Drive `Lidiya Memory`.
2. Development relay state and evidence: this GitHub branch.
3. `main` is never modified by this relay.
4. Short-term/candidate content must never override formal core or governance.

## File ownership

To avoid concurrent overwrite races, each role writes only its own relay output:

- Coordinator owns `control/MISSION_STATE.json` and `queue/A_TO_B.json`.
- Builder owns `queue/B_TO_C.json` and builder evidence files.
- Verifier owns `queue/C_TO_A.json` and verifier evidence files.
- `control/START.json` is the external start/resume signal.

A role may read every relay file but must not rewrite another role's owned packet.

## Packet lifecycle

`READY -> CLAIMED -> PRODUCED -> VERIFIED`

Packets require a unique `packet_id`, `mission_id`, `step_id`, source, target, timestamps, and evidence references. Duplicate `packet_id` values must not execute twice.

## Evidence-first rule

No slot may claim success from prose alone. Evidence should include, when applicable:

- exact files/paths inspected or changed
- source commit/ref
- diff or resulting file SHA
- commands/tests requested or run
- stdout/stderr/exit code when an execution environment exists
- acceptance criteria checked
- verifier decision and reason

If evidence cannot be independently checked, result is `DEFER`, not PASS.

## Lease/recovery rule

A task claim may include `lease_until`. If a worker disappears and the lease expires, a later worker may reclaim the same step, but it must preserve the original `packet_id` history and must not duplicate an already verified side effect.

## Safety boundary

Allowed autonomously in this branch: read-only inspection, specs, tests, patches, sandbox files, reversible development changes, handoffs, evidence records.

Always stop with `NEEDS_BOXUAN_APPROVAL` before: modifying formal personality/core/governance, permission expansion, accounts, credentials, money, destructive bulk deletion, merging PRs, production deployment, irreversible publishing, secret handling, or high-risk tools.

## First closed-loop mission

`LCR-V2-ROUNDTRIP-0001`

1. A consumes START and emits one harmless packet to B.
2. B validates packet fields and emits a structured ACK to C.
3. C independently checks A and B packet consistency.
4. C emits PASS to A.
5. A marks mission `PROJECT_DONE` only after C PASS.

Acceptance criteria:

- one START only
- A -> B -> C -> A observable in GitHub state
- same mission_id and step_id throughout
- no packet processed twice
- evidence exists for every transition
- no writes to `main`
- no human message required after START unless a safety gate or unrecoverable conflict occurs

## Next development after roundtrip

After the first roundtrip is verified, Coordinator should open the next sandbox mission in priority order:

1. durable deduplication and lease recovery
2. append-only evidence ledger
3. restart/resume test
4. bridge to existing `NAV-RELAY-MVP-0001`
5. optional local/offline mirror queue for Snow-Li / home-machine handoff
