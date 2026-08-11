# LCR-METABOLISM-0003 — Golden Triangle Status Panel

**Taiwan time authority:** Asia/Taipei (UTC+08:00)  
**Stage-2 start:** 2026-08-11 20:00  
**Hard deadline:** 2026-08-13 20:00  

## Current authoritative mirror

- Mission: `LCR-METABOLISM-0003`
- Step: `3`, attempt: `2`
- State: `READY_FOR_VERIFY`
- Current role: `LCR-C / GUARDIAN_VERIFIER`
- Pending packet: `packets/METABOLISM-0003-B-TO-C-STEP-003-REPAIR-001.json`
- Pending packet SHA-256: `b6ff4b05080636b6565676dcbeb8888970b90cf60ed7165cc06eef9c8a53b1ab`
- Builder repair handoff: `2026-08-12 01:46:00 Asia/Taipei`
- Builder Evidence: `evidence/METABOLISM-0003-STEP-003-BUILDER-REPAIR-001.json`
- Builder result: `BUILT_NOT_VERIFIED`
- Branch: `lidiya-cloud-relay-v2`
- Max formal slots: `3`; full-backup maximum: `2`
- Recovery baseline: `READ_ONLY`; Working exchange: `MUTABLE_COLLABORATION`; third full backup: `FORBIDDEN`

## STEP-003 repair candidate

C previously failed the first STEP-003 candidate because same-slot takeover did not require an explicit handoff action marker and authorization was only a caller-supplied boolean.

B repaired only `continuous_control.py` + `test_continuous_control.py`:

1. Handoff now requires explicit action exactly `SAME_SLOT_DURABLE_HANDOFF`.
2. Handoff `authorization_ref` must equal an independently supplied trusted durable authorization reference; bare `authorized=true` has no authority.
3. Missing/wrong action, forged bare boolean, missing/wrong authorization reference, bad state fingerprint, stale former worker and slot 4 are fail-closed.
4. Owner/user/collaborator input still cannot reset durable mission-control fields and raw body is not persisted.
5. Compact control truth still excludes raw chat/log/stale panels/duplicate self-reports.
6. External self-metabolism remains limited to allowlisted reproducible relay/workspace artifacts; protected/secret/hidden model/governance material quarantines.

Builder reproducible checks: `py_compile PASS`, `unittest 17/17 PASS`; exact local Git blob hashes match branch blobs. Independent C verification is now mandatory.

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
