# LCR-METABOLISM-0003 — Golden Triangle Status Panel

**Taiwan time authority:** Asia/Taipei (UTC+08:00)  
**Stage-2 start:** 2026-08-11 20:00  
**Hard deadline:** 2026-08-13 20:00  

## Current authoritative state

- Mission: `LCR-METABOLISM-0003`
- State: `READY_FOR_BUILDER`
- Current role: `LCR-B / METABOLISM_WORKER`
- Next role: `LCR-C / GUARDIAN_VERIFIER`
- Branch: `lidiya-cloud-relay-v2`
- Max slots: `3`
- Full-backup maximum: `2`
- Recovery baseline: `READ_ONLY`
- Working exchange: `MUTABLE_COLLABORATION`
- Third full backup: `FORBIDDEN`
- Main/default branch: `NO WRITE without explicit HUMAN sub-gate`

## Golden Triangle

`LCR-A Coordinator/Absorber → LCR-B Metabolism Worker → LCR-C Guardian Verifier → LCR-A`

Workers are replaceable. Durable State + Packet + Lease + Hash + Evidence is the subject.

## Time checkpoints (Asia/Taipei)

- T0: `2026-08-11 20:00` — authorization clock starts.
- T+24h: `2026-08-12 20:00` — midpoint health/recoverability checkpoint.
- T+42h: `2026-08-13 14:00` — final integration window; unresolved main/credential gates must already be explicit.
- T+48h: `2026-08-13 20:00` — deadline. Only verified `IDLE/PASS` counts as complete.

## First-stage formation acceptance

1. Machine-enforce `backup_count <= 2`.
2. B autonomously classifies/clears controlled low-risk stage garbage.
3. C independently blocks unsafe deletion.
4. A absorbs only verified compact metabolism output.
5. Three isolated slots hand off without duplicate consumption.
6. Worker loss/restart recovery is proven.
7. Real cloud `A→B→C→A` cleanup cycle is proven.
8. Metabolic Closure returns to `IDLE/PASS`.

## Candidate nutrition already present

A prior `LCR-METABOLISM-PHASE1-0003` workstream created a fail-closed cleanup engine and sandbox tests. It is **not a second authoritative mission**. It is treated as `WORKING_EXCHANGE` candidate nutrition and must be revalidated under `LCR-METABOLISM-0003`; duplicated or superseded pieces become Waste/Quarantine after verification.

## Update rule

Every worker wakeup must read `state/MISSION_STATE.json` first. This panel is a human-facing mirror; if it conflicts with durable state, durable state wins and this panel must be corrected.
