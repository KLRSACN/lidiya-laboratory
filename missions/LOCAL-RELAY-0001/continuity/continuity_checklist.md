# Continuity Static Validation Checklist

## Packet
- [ ] All required Task Packet fields exist.
- [ ] `additionalProperties` behavior is explicit.
- [ ] IDs are non-empty and match safe identifiers.
- [ ] `attempt >= 0`, `max_attempts >= 1`, and validator enforces `attempt <= max_attempts`.
- [ ] `5 <= lease_seconds <= 3600`.
- [ ] Payload path references are relative, traversal-free, and within authorized queue roots.

## State and lease
- [ ] Every implementation state maps to the protocol state table.
- [ ] No forbidden transition is reachable.
- [ ] State, packet hash, claim, attempts, and checkpoint are persisted before dependent actions.
- [ ] Heartbeat preserves owner and claim ID.
- [ ] Live leases cannot be reclaimed.
- [ ] Expired recovery increments generation or recovery count.
- [ ] Stale claims cannot submit results.

## Completion and recovery
- [ ] Canonical key is `mission_id::token::task_id`.
- [ ] Completion index records status, result_hash, completed_at, worker_id, attempt, outbox_path.
- [ ] Duplicate completed tasks return prior result without side effects.
- [ ] Retry is bounded and terminal failure is durable.
- [ ] Checkpoint identity/hash/progress are validated.
- [ ] Result and outbox writes are atomic or recoverably staged.
- [ ] Manifest hashes and claimed tests are checked against Builder Frozen Commit.

Final verdict must retarget the Builder Frozen Commit; this candidate alone cannot approve Builder.
