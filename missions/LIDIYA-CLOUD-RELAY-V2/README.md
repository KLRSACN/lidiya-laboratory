# LIDIYA CLOUD RELAY v2

Status: DESIGN/BOOTSTRAP
Base: NAV-RELAY-MVP-0001
Branch: `lidiya-cloud-relay-v2`

## Goal

One human START signal should be sufficient to let a cloud-hosted relay continue development without depending on the user's current laptop or a permanently open browser window.

The system uses three logical slots around one durable state store:

- **LCR-A / Coordinator** — chooses the next minimum verifiable task.
- **LCR-B / Builder** — implements only the assigned task and records evidence.
- **LCR-C / Verifier** — independently checks acceptance criteria and decides PASS/FAIL/DEFER/BLOCKED.
- **LCR-S / State Store** — durable, canonical execution state. Workers are replaceable; state is not.

```text
                    START
                      |
                      v
              +---------------+
              | LCR-A         |
              | Coordinator   |
              +-------+-------+
                      |
                      v
              +---------------+
              | LCR-S         |
              | State Store   |
              +---+-------+---+
                  |       ^
                  v       |
              +---+---+   |
              | LCR-B |---+
              |Builder|
              +---+---+
                  |
                  v
              +---+---+
              | LCR-C |
              |Verify |
              +---+---+
                  |
            PASS / FAIL
             |       |
             v       +------> B repair
             A
```

## Core invariant

**State is the subject; windows/runners are workers.**

No worker may rely on its local chat history as the source of truth. Every run starts by reading durable state and ends by writing an auditable packet.

## Home / School / Hospital / Reality mapping

- **Home (Google Drive)**: Identity Kernel, canonical memory, governance, stable architecture decisions.
- **School (development branch / sandbox)**: experiments, candidate code, failed attempts, temporary workspaces.
- **Hospital (Verifier / alternate model / tests)**: independent diagnosis, contradiction checks, drift checks, security checks.
- **Reality (CI, executable output, hardware/user result)**: actual tests and observable product behavior outrank model agreement.
- **Return Home**: only verified lessons and stable release metadata are promoted to canonical memory.

## Cognitive metabolism rule

Every relay cycle must distinguish **nutrients** from **waste**.

Keep:
- stable code or minimal patch
- acceptance evidence
- reproducible test command/result
- root-cause lesson
- rollback anchor
- provenance / hashes

Do not retain by default:
- full scratch conversations
- duplicate copies
- transient debug output
- obsolete candidates
- failed intermediate patches after their lesson is extracted
- stale model-generated assertions

Backup is not `keep everything`.

**Backup = proven recoverability.**

## State machine

```text
IDLE
  -> COORDINATING
  -> READY_FOR_BUILDER
  -> BUILDING
  -> READY_FOR_VERIFY
  -> VERIFYING
     -> FAIL -> READY_FOR_BUILDER
     -> PASS -> STEP_DONE -> COORDINATING
     -> DEFER/BLOCKED -> HUMAN_GATE
  -> PROJECT_DONE
  -> METABOLIZE
  -> NEXT_MISSION or IDLE
```

## Packet contract

Every packet must include:

- `schema_version`
- `mission_id`
- `run_id`
- `step_id`
- `attempt`
- `source_role`
- `target_role`
- `status`
- `parent_packet_sha256`
- `created_at`
- `lease_owner`
- `lease_expires_at`
- `task`
- `acceptance[]`
- `candidate_ref`
- `evidence[]`
- `result`
- `lesson`
- `disposition`

Packets are append/audit artifacts; `MISSION_STATE.json` is the current pointer.

## Lease rule

A task may be claimed by one worker at a time. The worker writes a lease before acting. An expired lease allows another runner to resume the same step from durable state.

No lease means no authority to mutate execution state.

## Version metabolism

### Constitutional Backup
Identity, governance, safety and canonical architecture. Slow-changing, explicit rollback.

### Stable Release
Known-good executable versions plus a small number of tested rollback anchors.

### Candidate / School Build
Temporary development versions. Must have parent version, purpose, owner/run, test evidence, TTL and final disposition.

### Disposable Workbench
Scratch patches, logs, caches and intermediate outputs. Deleted after evidence/lesson extraction unless specifically retained for an incident.

## Cloud execution direction

Preferred implementation path:

1. GitHub is the durable execution ledger and code host.
2. GitHub Actions provides cloud runners after the laptop disconnects.
3. AI workers run in isolated invocations rather than relying on browser chat persistence.
4. The initial cloud engine can be Gemini because the work-machine agent is `雪璃`; engine identity is not the canonical personality.
5. GitHub Agentic Workflows (`gh-aw`) is the preferred hardened target because it supports Gemini/Codex/Copilot/Claude, sandboxed agent execution and validated safe outputs.
6. Until `gh-aw` is compiled/activated, a standard Actions bootstrap may be used only on the development branch with strict path/branch guards.

## Safety / write boundaries

- Never autonomously merge to `main`.
- Autonomous Builder writes only to a dedicated mission/candidate branch.
- Verifier never trusts Builder's self-reported PASS.
- `PROJECT_DONE` requires executable evidence, not model consensus.
- Identity/personality files are outside Builder write scope.
- A failed or ambiguous reality test stops promotion and returns to Builder or HUMAN_GATE.
- Secrets must never be written into packets/logs.

## First proof mission

`LCR-ROUNDTRIP-0001`

Acceptance:

1. A reads state and creates exactly one task packet for B.
2. B claims it once, creates a deterministic harmless candidate artifact, records evidence, and routes to C.
3. C independently validates artifact content/hash and acceptance criteria.
4. C PASS routes back to A.
5. A marks mission done and runs metabolism cleanup.
6. Duplicate delivery does not execute the same step twice.
7. A killed worker can resume after lease expiry.
8. No second human message is required after START.

Only after this proof passes should real Lidiya development missions enter the relay.
