# LCR-METABOLISM-0003 — Golden Triangle Status Panel

**Taiwan time authority:** Asia/Taipei (UTC+08:00)  
**Stage-2 start:** 2026-08-11 20:00  
**Hard deadline:** 2026-08-13 20:00  

## Current authoritative state

- Mission: `LCR-METABOLISM-0003`
- State: `READY_FOR_VERIFY`
- Current role: `LCR-C / GUARDIAN_VERIFIER`
- Builder result: `BUILT_NOT_VERIFIED`
- B→C packet SHA-256: `1cc809872754c518f4f721c738bb4cad622bf94d9bb6bdbb314500c323911252`
- Branch: `lidiya-cloud-relay-v2`
- Max slots: `3`
- Full-backup maximum: `2`
- Recovery baseline: `READ_ONLY`
- Working exchange: `MUTABLE_COLLABORATION`
- Third full backup: `FORBIDDEN`
- Main/default branch: `NO WRITE without explicit HUMAN sub-gate`

## STEP-001 Builder evidence

- Candidate: `metabolism_guard.py` + `test_metabolism_guard.py`
- GitHub readback blob SHAs: `e9669e8599771e4b6e0ba5fc2792f357b11dffb5` / `e6066fc0652230945a3f6cd0956ae29ec91c130d`
- Builder reproduction: `py_compile=0`, `13/13 tests PASS`
- Safe fixture deletion: observed
- Unique/protected fixture retention: observed
- Third full backup rejection: observed
- Builder did **not** declare PASS. Exact repository-byte verification is assigned to LCR-C.

## Golden Triangle

`LCR-A Coordinator/Absorber → LCR-B Metabolism Worker → LCR-C Guardian Verifier → LCR-A`

Workers are replaceable. Durable State + Packet + Lease + Hash + Evidence is the subject.

## Time checkpoints (Asia/Taipei)

- T0: `2026-08-11 20:00` — authorization clock starts.
- T+24h: `2026-08-12 20:00` — midpoint health/recoverability checkpoint.
- T+42h: `2026-08-13 14:00` — final integration window; unresolved main/credential gates must already be explicit.
- T+48h: `2026-08-13 20:00` — deadline. Only verified `IDLE/PASS` counts as complete.

## First-stage formation acceptance

1. Machine-enforce `backup_count <= 2` — **BUILT, awaiting C verification**.
2. B autonomously classifies/clears controlled low-risk stage garbage — **fixture BUILT, awaiting C verification**.
3. C independently blocks unsafe deletion — **pending**.
4. A absorbs only verified compact metabolism output — pending.
5. Three isolated slots hand off without duplicate consumption — in progress.
6. Worker loss/restart recovery is proven — pending.
7. Real cloud `A→B→C→A` cleanup cycle is proven — pending.
8. Metabolic Closure returns to `IDLE/PASS` — pending.

## Candidate nutrition already present

A prior `LCR-METABOLISM-PHASE1-0003` workstream is **not a second authoritative mission**. It remains `WORKING_EXCHANGE` candidate nutrition and must be revalidated under `LCR-METABOLISM-0003`; duplicated or superseded pieces become Waste/Quarantine only after verification.

## Update rule

Every worker wakeup must read `state/MISSION_STATE.json` first. This panel is a human-facing mirror; if it conflicts with durable state, durable state wins and this panel must be corrected.
