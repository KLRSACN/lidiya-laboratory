# Minimal Patch Plan

This document does not modify `candidate-v0.2`.

If WINDOW-02 reports `NEEDS_CORRECTION`, create a newly authorized version path and patch only the smallest owning module:

| Problem type | Minimum file | Minimum action | Required targeted test |
|---|---|---|---|
| Atomic claim or lease fencing | `relay_storage_v0_2.py` | Change `claim_next`, `_validate_live_claim`, or `heartbeat` only | atomic-race plus stale-owner test |
| Outbox/registry transaction ordering | `relay_transaction_v0_2.py` | Change journal or publication sequence only | all three crash boundaries |
| Restart reconciliation | `relay_recovery_v0_2.py` | Change `_reconcile_assignment` or `reconcile` only | outbox-only, registry-only, conflict tests |
| Hash or packet identity | `relay_common_v0_2.py` or `relay_storage_v0_2.py` | Change canonical identity fields only | hash, retry, and token-isolation tests |
| Auditor interface mismatch | thin adapter in a newly authorized path | Add aliases without changing transaction semantics | adapter contract tests |
| Manifest mismatch | new manifest in a newly authorized path | Recompute size and SHA-256 from exact bytes | inventory verification |

For any correction:

1. Preserve all 24 existing tests.
2. Add one regression test reproducing the reported defect.
3. Run in a temporary isolated runtime root.
4. Publish only after WINDOW-00 authorizes a new path and commit requirement.
