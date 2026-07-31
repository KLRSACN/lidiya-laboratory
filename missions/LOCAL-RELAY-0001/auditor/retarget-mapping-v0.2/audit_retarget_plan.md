# Audit Retarget Plan v0.2

## Status

Mapping only. No final audit verdict is authorized.

## Source

- Builder candidate: `35988ad594d725aed4e5f907ba1d050385135a6f`
- Auditor preparation: `d41ddebf8dbdfe61451638737cccead2d109f7a2`

## Retarget configuration

### fault_injection_harness.py

Use a thin CLI adapter importing `LocalRelayDispatcherV02` from an isolated Builder copy. Map `claim` to packet materialization in the isolated inbox plus `claim_next`. Map result submission to `execute_claim`.

Direct Builder fault hooks:

- `after_journal_before_outbox`
- `after_outbox_before_registry`
- `after_registry_before_journal_commit`

Use isolated monkeypatching for `os.fsync`, `os.replace`, partial writes, and checkpoint-destination failures. Never patch repository files.

### lease_fencing_harness.py

Candidate v0.2 supports owner, `claim_id`, running-path and lease-expiry validation. It does not provide numeric `lease_generation`. Therefore generation-1/generation-2 fencing cannot be claimed as contract-complete and must remain blocked pending a new Frozen Commit.

### manifest_verifier.py

Target `missions/LOCAL-RELAY-0001/builder/candidate-v0.2/manifest.json` from one Frozen Commit. Materialize every declared entry, calculate byte size and SHA-256, detect missing, extra and duplicate paths, and enforce the manifest self-entry rule. Git blob SHA must not be treated as SHA-256.

## Adapter limitations

- `read_task_state()` is absent.
- `read_checkpoint()` can read the file but cannot satisfy required `task_id` and `highest_progress_token` fields without inventing evidence.
- `read_completed_record()` requires a packet-identity wrapper and output normalization.

## Gate

Wait for WINDOW-02 continuity approval and WINDOW-00 publication of a new Builder Frozen Commit. Retarget all reads to that single Commit before mutation-based testing in an isolated runtime root.
