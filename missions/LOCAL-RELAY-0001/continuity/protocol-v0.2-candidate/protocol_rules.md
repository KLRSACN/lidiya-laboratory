# Local Relay Dispatcher Protocol v0.2 Candidate

Mission: `LOCAL-RELAY-0001`
Token: `RELAY-BOOTSTRAP-0001`
Generation: `1`

## Normative decisions

1. **Task action enum**: `WRITE_TEXT`, `RETRY`, `RECOVER`, `CANCEL`.
   Runtime may support a subset, but unsupported actions must be quarantined before `RUNNING`.

2. **target_worker**: accepts `WINDOW-NN` or `ANY`. `ANY` means any authorized worker may claim once.

3. **Task Packet vs Runtime Envelope**
   - Task Packet: immutable assignment fields only.
   - Runtime Envelope: `packet_sha256`, `lease`, `failure_reason`, dispatcher annotations.
   - Runtime fields must not be accepted as untrusted Task Packet input.

4. **Lease bounds**: `lease_seconds` MUST be integer `5..3600`.

5. **Required strings**: `mission_id`, `token`, `task_id`, `target_worker`, `action`,
   `objective`, and every success/evidence item MUST be non-empty after trimming.

6. **Time format**: RFC 3339 / ISO 8601 UTC with `Z`, e.g. `2026-07-31T00:00:00Z`.
   Fractional seconds are allowed. Naive timestamps and non-UTC offsets are rejected.

7. **success_criteria / evidence_required**: arrays with at least one non-empty string each.

8. **Runtime / Queue Root authorization**
   - Runtime root MUST resolve beneath an explicitly configured allowlisted root.
   - Queue paths and output paths MUST be relative.
   - Absolute paths, drive-qualified paths, UNC paths, NUL, and `..` segments are rejected.
   - Every resolved path MUST remain beneath runtime root.

9. **Lease identity**
   - `claim_id`: globally unique immutable identifier for one claim.
   - `lease_generation`: starts at 0 and increments on every expired reclaim.
   - `recovery_count`: monotonic count of recovery operations.
   - Heartbeat preserves owner, claim_id, lease_generation.
   - Result submission requires current owner, claim_id, generation, and unexpired lease.

10. **Completed registry**
    - Unique key: `mission_id::token::task_id`.
    - Required: status, result_hash, completed_at, worker_id, attempt, outbox_path.
    - `result_hash` is SHA-256 of canonical result or produced artifact as declared.
    - `outbox_path` is safe relative path beneath runtime root.
    - Outbox and registry must be recoverably consistent through journal or deterministic reconciliation.
