# LOCAL-RELAY-0001 Formal Continuity Verification

- Mission: `LOCAL-RELAY-0001`
- Token: `RELAY-BOOTSTRAP-0001`
- Generation: `1`
- Builder frozen commit: `9ca051a4bd5e4a4e6aa293a215d19b4f235042f5`
- Protocol candidate commit: `a0ad0fed0580291e96f94704dac8f4ef21cbdff0`
- Verdict: `NEEDS_CORRECTION`
- Method: frozen-commit static read only; no tests or live trigger executed.

## Identity and manifest

Builder manifest declares the expected mission, token, generation, and Wake Core commit `f1f116fa92ebfc45987fb3b3f74f295b3a497d6a`. Eight listed artifacts were readable from the frozen commit. Manifest-listed byte sizes and SHA-256 values were inspected, but this connector session did not expose a raw-byte materialization path for an independent local SHA-256 recomputation; therefore cryptographic recomputation remains an open verification item rather than being promoted to confirmed.

## Compatible behavior

- `attempt <= max_attempts` is enforced in `valid()`.
- Atomic claim uses same-filesystem `os.replace`; the included race test expects one winner.
- Output path rejects absolute paths and `..`, and writes resolve below Runtime Root.
- Retry increments attempt and stops when the incremented value reaches `max_attempts`.
- Completed-registry or existing-outbox checks suppress ordinary duplicate execution.
- Malformed, missing-field, bad-hash, and unsupported-action packets are quarantined before task execution.
- JSON writes use temp file, fsync, and atomic replace.

## Protocol incompatibilities

1. Task Packet schema conflict:
   - Protocol action enum is `DISPATCH|RETRY|RECOVER|CANCEL`; Builder accepts only `WRITE_TEXT`.
   - Protocol target requires `WINDOW-NN`; Builder additionally accepts `ANY`.
   - Protocol has `additionalProperties=false`; Builder packet uses `packet_sha256` and later `lease` / `failure_reason` fields not admitted by that schema.
   - Protocol lease range is 5..3600 seconds; Builder accepts any integer >=1 and has no upper bound.
   - Builder does not enforce non-empty mission_id, token, task_id, target_worker, objective, success criteria, or evidence list, and does not validate created_at format.

2. Lease protocol conflict:
   - Builder lease lacks `claim_id`, `lease_generation`, and `recovery_count`.
   - Heartbeat verifies owner but does not reject an already expired lease.
   - Execution verifies owner only; it does not verify expiry, claim_id, generation, or current persisted lease authority.
   - Recovery increments attempt, but not lease generation or recovery count.
   - A stale worker can potentially submit during a recovery race because execute has no expiry/current-generation guard.

3. State-machine conflict:
   - Builder persistence does not model the required states `RECEIVED`, `VALIDATED`, `CLAIMED`, `RETRY_PENDING`, `RECOVERY_PENDING`, or `QUARANTINED` as canonical per-task state records.
   - Queue directory movement approximates states but does not satisfy the protocol's required persistent task-state fields and forbidden-transition checks.

4. Checkpoint and dispatcher-state conflict:
   - Builder checkpoint contains only assignment_key, owner, current_state, attempt, and lease_expires_at.
   - It lacks mission_id, token, task_id, progress token, next action, completed/pending steps, result hash, recoverable, checkpoint hash, updated_at, claim_id, and lease generation.
   - Dispatcher state contains only completed_assignments; it lacks mission identity, generation, updated_at, canonical task records, lease counters, and protocol-compliant completed index structure.

5. Completion registry conflict:
   - Completed records lack required `outbox_path`.
   - No explicit consistency reconciliation exists among running file, checkpoint, outbox, and completed registry.

## Crash consistency

The completion order is:

1. write side-effect output;
2. write Outbox result;
3. write Completed Registry;
4. delete Running claim.

If the process crashes after step 2 and before step 3, restart/claim logic sees the existing Outbox and suppresses rerun, then removes the Running file and may emit a duplicate marker. This avoids a second ordinary side effect, but leaves the Completed Registry permanently missing and does not backfill it from Outbox. The protocol requires consistent Outbox and completion index state. The current behavior is therefore not acceptable as final continuity semantics.

A safe correction must implement one of:

- transactional/journaled completion with recovery reconciliation; or
- Outbox-as-authority recovery that validates the result hash and atomically backfills Completed Registry before deleting Running; or
- a single atomic completion record from which Outbox and Registry are deterministically reconstructed.

## Required corrections

1. Align Task Packet action, target, additionalProperties, lease bounds, and required field validation with the published protocol, or publish an explicitly versioned protocol amendment.
2. Add claim_id, lease_generation, recovery_count, expiry validation, and stale-claim rejection at heartbeat and result submission.
3. Persist canonical task states and enforce allowed/forbidden transitions.
4. Implement protocol-compliant checkpoint and dispatcher-state records with hashes and recovery metadata.
5. Add outbox_path and reconciliation semantics to the completed index.
6. Repair the Outbox-before-Registry crash window with deterministic recovery and add a fault-injection test for that exact boundary.
7. Recompute and independently verify all manifest file byte sizes and SHA-256 values in the next frozen candidate.
