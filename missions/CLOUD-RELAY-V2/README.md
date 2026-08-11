# LIDIYA CLOUD RELAY v2

Cloud-first three-slot relay for autonomous, resumable Lidiya development.

## Goal

One human START signal should be enough to keep a mission moving through three independent worker slots without relying on any browser window's chat memory.

- **LCR-A / COORDINATOR**: decides the next minimal verifiable step and owns mission progression.
- **LCR-B / BUILDER**: performs one low-risk reversible implementation step and records evidence.
- **LCR-C / VERIFIER**: independently checks acceptance criteria and returns PASS or FAIL.
- **LCR-S / STATE STORE**: GitHub branch state plus evidence. Google Drive remains the authority for Lidiya governance, memory, and handoff context.

## Source of truth

Development relay state lives on branch `cloud-relay-v2` under this directory. Formal personality, governance, approved memory, account authority, financial authority, deletion authority, production release authority, and other high-risk decisions do **not** move into this branch and remain governed by Lidiya Memory / Boxuan approval.

## Relay loop

```text
START
  -> COORDINATOR
  -> BUILDER
  -> VERIFIER
       PASS -> COORDINATOR -> next step
       FAIL -> BUILDER -> VERIFIER

PROJECT_DONE
  -> archive evidence
  -> propose next mission
  -> start only low-risk approved work automatically
```

## Files

- `control/START.json`: start/resume signal and safety mode.
- `state/MISSION_STATE.json`: canonical current mission state.
- `state/RELAY_PACKET.json`: one current routable packet.
- `state/EVIDENCE/`: immutable-per-step evidence files when used by workers.
- `handoff/COORDINATOR.md`: LCR-A contract.
- `handoff/BUILDER.md`: LCR-B contract.
- `handoff/VERIFIER.md`: LCR-C contract.
- `cloud_relay.py`: local/offline-compatible JSON relay engine with leases and packet hashes.
- `test_cloud_relay.py`: round-trip, duplicate-consume, wrong-target, and fail-route tests.

## Safety boundary

Automatic work is limited to low-risk, reversible development and verification on the development branch/sandbox. The relay must stop with `NEEDS_BOXUAN_APPROVAL` for:

- personality-core or governance changes;
- permission expansion;
- accounts, credentials, secrets, or money;
- destructive/bulk deletion;
- merging to protected/default branches;
- production deployment or irreversible publication;
- high-risk third-party tooling.

## Lease and deduplication

Each worker claims a short lease before changing state. A packet contains an integrity hash and can be consumed only once. If a lease expires, a later worker may safely resume. Chat content is not the source of truth.

## MVP acceptance

Mission `CLOUD-RELAY-V2-ROUNDTRIP-0001` succeeds when:

1. Coordinator dispatches exactly one step to Builder.
2. Builder writes evidence and hands off to Verifier.
3. Verifier independently returns PASS to Coordinator.
4. Re-consuming a packet is rejected.
5. The process needs no second human message after START.

## Local test

```bash
cd missions/CLOUD-RELAY-V2
python -m unittest -v test_cloud_relay.py
```

The same JSON state format is intentionally usable by a future offline mirror using local Git + Python + SQLite/Ollama when Internet connectivity is unavailable.
