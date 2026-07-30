# LOCAL-RELAY-0001 Independent Audit Plan

## Scope

This harness validates a filesystem-backed local dispatcher from a frozen Builder commit. It does not modify Builder or Continuity artifacts and does not test browser, ChatGPT, GitHub polling, or external AI services.

## Required adapter contract

The Builder candidate must expose a CLI or a thin audit adapter with operations equivalent to:

- `enqueue(packet_path, queue_root)`
- `claim(queue_root, owner_id, lease_seconds)`
- `heartbeat(queue_root, task_id, owner_id, lease_seconds)`
- `complete(queue_root, task_id, owner_id, result_path)`
- `recover(queue_root, now)`
- `dispatch_once(queue_root, owner_id)`

The final audit may provide a read-only adapter in the isolated test copy. It must not patch the frozen Builder source.

## Dynamic tests

1. Atomic Claim Race: launch two independent Python processes with a shared start barrier. Exactly one claim may succeed.
2. Worker Crash: terminate the claiming process after durable running/lease state but before completion; verify artifact retention and recovery after expiry.
3. Lease Safety: reject premature recovery, permit expired recovery, reject stale-owner completion, and verify heartbeat extension.
4. Duplicate Delivery: replay identical mission/token/task_id after completion; verify no new side effect and unchanged outbox hash.
5. Process Restart: kill the dispatcher process and start a new process against the same disk state; verify running/completed/retry restoration.
6. Retry Exhaustion: inject persistent failure; verify monotonic attempts, transition to failed at max_attempts, and no inbox requeue.
7. Corrupt Input: truncated JSON, non-JSON, missing fields, wrong types, hash mismatch, and path traversal must be quarantined before RUNNING.
8. Partial Write: `.tmp`/partial packets must be invisible; only atomic replacement to the final packet name becomes claimable.
9. Concurrent Dispatcher Restart: replacement dispatcher must respect a valid lease and avoid duplicate claim.
10. Result Commit Safety: result staging and atomic replacement must not allow completed registry/outbox divergence.

## Evidence rules

Each test records process IDs, exact command, exit codes, stdout/stderr, directory snapshots, file hashes, monotonic timestamps, and final registry states. Thread-only simulations do not satisfy concurrency tests.

## Verdict boundary

No implementation is approved until the Builder publishes a frozen commit and both the official tests and this independent fault-injection suite pass against an isolated copy.
