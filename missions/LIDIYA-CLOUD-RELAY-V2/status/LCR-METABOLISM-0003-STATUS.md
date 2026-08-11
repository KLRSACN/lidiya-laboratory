# LCR-METABOLISM-0003 — Golden Triangle Status Panel

**Taiwan time authority:** Asia/Taipei (UTC+08:00)  
**Stage-2 start:** 2026-08-11 20:00  
**Hard deadline:** 2026-08-13 20:00  

## Current authoritative mirror

- Mission: `LCR-METABOLISM-0003`
- Step: `3`, attempt: `0`
- State: `READY_FOR_BUILDER`
- Current role: `LCR-B / METABOLISM_WORKER`
- Pending packet: `packets/METABOLISM-0003-A-TO-B-STEP-003.json`
- Pending packet SHA-256: `c0529834b8b6c801acba5721a38bcb84d33581c1c5a90c5b7ff4d7fc71909018`
- Last verified handoff: STEP-002 C PASS at `2026-08-12 01:23:45 Asia/Taipei`
- Branch: `lidiya-cloud-relay-v2`
- Max formal slots: `3`; full-backup maximum: `2`
- Recovery baseline: `READ_ONLY`; Working exchange: `MUTABLE_COLLABORATION`; third full backup: `FORBIDDEN`

## STEP-003 objective

Machine-enforce the continuous-control rules requested for the Golden Triangle:

1. Formal roster is exactly `LCR-A / LCR-B / LCR-C`; slot 4 is rejected.
2. A new authorized worker/window may replace B or C only through `SAME_SLOT_DURABLE_HANDOFF` with generation + durable-state fingerprint; the former worker becomes stale and cannot act afterward.
3. Incoming owner/user/collaborator control input must not reset `mission_id / status / step / current_role / pending packet/hash / lease`.
4. Durable control-input records keep metadata/fingerprint only; the raw message body is not persisted as control-state truth.
5. Primary control-console self-metabolism is limited to controllable external relay/workspace metadata. Compact durable output keeps current Mission, latest verified Evidence pointer, pending packet/hash, Lease, rollback, blocker and root-cause lesson; raw chat, duplicate self-reports, stale panels and raw logs are excluded.
6. Hidden model/system state is not a cleanup target. Secrets, protected evidence, rollback/stable, durable-referenced, unique human work, unreproducible material, Identity/Personality/Governance and ambiguous provenance fail closed.

Builder scope is only `continuous_control.py` + `test_continuous_control.py`. B may return only `BUILT_NOT_VERIFIED`; independent C verification is mandatory.

## Platform wake / worker proof

Task-scoped read-only launcher is active only at `.github/workflows/lcr-cloud-launcher.yml`; all other main paths remain forbidden. Authoritative Reality run `31516866778` instantiated separate A/B/C GitHub-hosted jobs successfully with repository write permission=false. Artifact `9111401445` records the wake ACK. New windows still do not create a fourth formal slot.

Cross-window live-link nonce `LCR-LINK-20260811-2342-7F3A` has a real Builder `CONNECT_ACK` to `ONLINE-LIDIYA-SECONDARY-INTEGRATOR`; Secondary remains read-only support until a same-slot durable handoff assigns formal B or C authority.

## Continuous-control rule

Receiving owner messages, collaborator reports or replacement-window requests is a **control input, not a STOP event**. Durable State + Packet + Lease + Hash + Evidence remains authoritative while the conversation continues.

## Time checkpoints (Asia/Taipei)

- T0: `2026-08-11 20:00`
- T+24h: `2026-08-12 20:00`
- T+42h: `2026-08-13 14:00`
- T+48h: `2026-08-13 20:00` — only verified `IDLE/PASS` counts as complete.

## Update rule

Every worker wakeup reads `state/MISSION_STATE.json` first. This file is human-facing only; durable state wins on any conflict and the next authorized role must correct the mirror.
