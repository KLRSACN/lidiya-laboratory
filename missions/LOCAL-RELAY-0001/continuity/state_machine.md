# Local Relay Dispatcher v0.1 — State Machine

Canonical key: `mission_id::token::task_id`.

| State | Allowed next | Required condition | Persist before transition | Forbidden |
|---|---|---|---|---|
| RECEIVED | VALIDATED, QUARANTINED | packet atomically discovered | packet hash, inbox path, received_at | direct RUNNING/COMPLETED |
| VALIDATED | CLAIMED, FAILED, QUARANTINED | schema and cross-field invariants pass | normalized packet, validation result | claim without valid packet |
| CLAIMED | RUNNING, RECOVERY_PENDING | atomic lease acquired | owner, claim_id, timestamps, lease_generation | second live owner |
| RUNNING | COMPLETED, RETRY_PENDING, FAILED, RECOVERY_PENDING, QUARANTINED | current non-expired claim matches | heartbeat, progress/checkpoint, side-effect guard | result from stale claim |
| COMPLETED | — | result persisted, hashed, indexed, outbox atomically written | completion index and result hash | retry or overwrite |
| RETRY_PENDING | CLAIMED, FAILED, QUARANTINED | attempt < max_attempts and backoff elapsed | attempt, error, next_retry_at | immediate unbounded retry |
| FAILED | — | attempts exhausted or terminal error | terminal reason, evidence | transition back to RUNNING |
| QUARANTINED | RECOVERY_PENDING, FAILED | corrupt/unsafe/ambiguous packet isolated | quarantine path, reason, original hash | normal claim |
| RECOVERY_PENDING | CLAIMED, FAILED, QUARANTINED | prior lease expired or crash checkpoint valid | recovery_count, new generation, recovery evidence | reuse expired claim |

## Recovery rules

1. A valid, unexpired lease is never reclaimed.
2. Expired recovery creates a new claim and increments `lease_generation` or `recovery_count`.
3. The old worker cannot heartbeat or submit with an expired `claim_id`.
4. `COMPLETED` is immutable for the canonical key. Re-delivery returns the indexed result without re-running side effects.
5. Checkpoint identity, hash, and progress monotonicity are verified before resume.
6. Side effects are permitted only after durable state is `RUNNING`, claim identity is current, lease is unexpired, and completion index is absent.
7. Corrupt packets and unauthorized paths move to `QUARANTINED`; they are never guessed or repaired in place.
