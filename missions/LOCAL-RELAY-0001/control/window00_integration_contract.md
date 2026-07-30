# WINDOW-00 Integration Contract

MISSION_ID: LOCAL-RELAY-0001
TOKEN: RELAY-BOOTSTRAP-0001
OWNER: WINDOW-00 / MAIN-LIDIYA
STATUS: ACTIVE

## Scope

WINDOW-00 owns the integration boundary between Local Relay Dispatcher v0.1 and the future Trigger Adapter v0.1. This file does not authorize Live Trigger, browser control, ChatGPT window control, or external API execution.

## Deliverables owned by WINDOW-00

1. Canonical acceptance gates for Builder, Continuity, and Auditor outputs.
2. Conflict resolution rules between implementation, protocol schemas, and fault-injection expectations.
3. Dispatcher-to-Trigger Adapter interface contract.
4. Final handoff package for the next MAIN-LIDIYA window.

## Dispatcher Acceptance Gates

A candidate cannot be approved unless all of the following are independently verified:

- Atomic claim allows exactly one winner across independent processes.
- Running tasks persist on disk and survive process restart.
- Lease owner, claim id, generation, heartbeat, and expiry are durable.
- Unexpired leases cannot be reclaimed.
- Expired leases can be recovered without allowing the former owner to commit a result.
- Retry counters are monotonic and stop at max_attempts.
- Duplicate mission_id + token + task_id cannot repeat side effects after completion.
- Corrupt or invalid packets never enter RUNNING.
- Task and result writes use temporary files followed by atomic replacement.
- Runtime paths are restricted to the configured runtime root.
- Completed registry and outbox result cannot disagree after a successful commit.
- Official tests and independent auditor tests both pass from the same Frozen Commit.

## Conflict Resolution Priority

When Builder implementation, Continuity schemas, and Auditor expectations conflict, WINDOW-00 resolves them in this order:

1. Safety and durable state integrity.
2. mission_control.json authority.
3. Frozen Wake Core v0.2 semantics.
4. Protocol schema correctness.
5. Builder implementation convenience.

No party may silently redefine mission identity, token identity, task identity, lease ownership, or completion semantics.

## Dispatcher-to-Trigger Adapter Interface

The Trigger Adapter may only enqueue a complete immutable Task Packet into runtime/inbox through a temporary file and atomic rename.

Required adapter output fields:

- mission_id
- token
- task_id
- trigger_id
- trigger_type
- trigger_observed_at
- target_worker
- action
- objective
- attempt
- max_attempts
- lease_seconds
- payload
- success_criteria
- evidence_required
- packet_hash

The Trigger Adapter must not:

- modify running tasks;
- write directly to outbox, failed, checkpoints, or completed registry;
- bypass packet validation;
- execute the task itself;
- reuse a completed mission_id + token + task_id combination;
- create browser or ChatGPT UI side effects.

Initial trigger types reserved for the next stage:

- SCHEDULE
- FILE_EVENT
- HEALTH_EVENT
- GITHUB_TASK_FILE

GITHUB Issue polling, OpenAI API, Claude API, LINE, email, and browser adapters remain outside LOCAL-RELAY-0001.

## Handoff Conditions

Before WINDOW-00 hands control to a new MAIN window, the following references must be recorded:

- mission_control.json commit;
- Builder Frozen Commit or current Builder state;
- Continuity candidate/final commit and verdict;
- Auditor harness commit and final verdict;
- WINDOW-00 final integration verdict;
- unresolved issues and exact next action;
- Google Drive integration document id.

## Current State

- Wake Core v0.2: APPROVED
- Local Relay Dispatcher Builder: DISPATCHED TO WINDOW-01
- Protocol Candidate: DISPATCHED TO WINDOW-02
- Audit Harness: DISPATCHED TO WINDOW-03
- WINDOW-00 Integration Contract: PUBLISHED
- Live Trigger: NOT STARTED
