# Local Relay Dispatcher candidate-v0.2

This candidate is a copy-based correction built from frozen builder commit `9ca051a4bd5e4a4e6aa293a215d19b4f235042f5`.

## Crash consistency

Each successful assignment uses a durable transaction journal:

1. atomically write the deterministic `WRITE_TEXT` effect;
2. persist a `PREPARED` journal containing the exact result and hashes;
3. atomically publish Outbox;
4. atomically update Completed Registry;
5. mark the journal `COMMITTED`.

Startup reconciliation repairs Outbox-only, Registry-only, and PREPARED-journal states when their identities and hashes agree. Conflicting durable records are blocked and a diagnostic is placed in quarantine.

## Stale owner protection

Each atomic claim receives a unique `claim_id`. Commit requires matching owner, matching claim ID, an existing running file, and an unexpired lease. After recovery/reclaim, the former worker cannot publish.

## Scope

Only the bounded local `WRITE_TEXT` worker stub is supported. No live ChatGPT trigger, browser control, external AI API, GitHub polling, HOME modification, or Trigger Adapter is included.
