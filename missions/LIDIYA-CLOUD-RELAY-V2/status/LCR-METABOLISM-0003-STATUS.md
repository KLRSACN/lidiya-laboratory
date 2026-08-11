# LCR-METABOLISM-0003 — Golden Triangle Status Panel

**Taiwan time authority:** Asia/Taipei (UTC+08:00)  
**Stage-2 start:** 2026-08-11 20:00  
**Hard deadline:** 2026-08-13 20:00  

## Current authoritative mirror

- Mission: `LCR-METABOLISM-0003`
- Step: `2`, repair attempt: `1`
- State: `READY_FOR_VERIFY`
- Current role: `LCR-C / GUARDIAN_VERIFIER`
- Builder result: `BUILT_NOT_VERIFIED`
- Pending packet: `packets/METABOLISM-0003-B-TO-C-STEP-002-REPAIR-001.json`
- Pending packet SHA-256: `9aa639937330108f30ea806e3261fbe7222b67154b29980761a5a272b3aad2bf`
- Branch: `lidiya-cloud-relay-v2`
- Max slots: `3`; full-backup maximum: `2`
- Recovery baseline: `READ_ONLY`; Working exchange: `MUTABLE_COLLABORATION`; third full backup: `FORBIDDEN`
- Main/default branch: `NO WRITE without explicit HUMAN sub-gate`

## STEP-002 repair

LCR-C previously failed STEP-002 because packet integrity trusted a claimed hash, restart recovery did not retain the exact next handoff identity, and this panel was stale. LCR-B repair attempt 1 now derives packet SHA-256 from canonical packet content excluding `packet_sha256`, rejects mutated content carrying a stale claimed hash, persists exact next pending packet path/hash during dispatch, and exposes durable-state-only restart recovery. Focused Builder reproduction for the two repaired failure modes: `2/2 PASS`. Full independent verification remains assigned to LCR-C.

Candidate blob SHAs:
- `golden_triangle_orchestrator.py`: `58c57353d1dcf298810fb93f69dd60c6ab8be97b`
- `test_golden_triangle_orchestrator.py`: `2b05207674f2a976e4bfcff700f7991ec5386db9`

## Golden Triangle

`LCR-A Coordinator/Absorber → LCR-B Metabolism Worker → LCR-C Guardian Verifier → LCR-A`

New authorized windows replace an existing slot only through durable same-slot handoff; they never create slot 4. Workers are replaceable. Durable State + Packet + Lease + Hash + Evidence is authoritative.

## Time checkpoints (Asia/Taipei)

- T0: `2026-08-11 20:00`
- T+24h: `2026-08-12 20:00`
- T+42h: `2026-08-13 14:00`
- T+48h: `2026-08-13 20:00` — only verified `IDLE/PASS` counts as complete.

## Update rule

Every worker wakeup reads `state/MISSION_STATE.json` first. This file is only a human-facing mirror; durable state wins on conflict and the next authorized worker must correct the mirror.
