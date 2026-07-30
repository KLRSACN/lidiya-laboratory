# Crash Recovery Oracle v0.2

## Required cases

1. Before side effect: resume or retry once under a valid lease; no completed record may exist.
2. After side effect and before outbox: detect and hash the artifact, then create outbox without repeating the side effect.
3. After outbox and before registry: use outbox as durable evidence, backfill the completed registry, then clean the running record.
4. After registry and before running cleanup: verify registry and outbox agree, then remove the stale running record without repeating work.
5. During checkpoint update: accept only the old complete checkpoint or the new complete checkpoint; reject partial or corrupt data.
6. During lease recovery: recovery must be idempotent and increment lease_generation and recovery_count exactly once.
7. Stale owner heartbeat: reject when owner, claim_id, generation, or expiry no longer matches the current lease.
8. Stale owner result submission: reject when owner, claim_id, generation, or expiry no longer matches the current lease.

## Consistency rule

Completion must use a write-ahead journal with idempotent replay, or deterministic startup reconciliation across running, outbox, registry, checkpoint, and output hash. Outbox existence alone is insufficient unless registry backfill and stale-running cleanup are guaranteed.
