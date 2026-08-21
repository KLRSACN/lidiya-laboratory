# Gearbox Clock Epoch Recovery V04 Development Note

Status: CANDIDATE_ONLY / ORIGINAL_V03_READ_ONLY

This branch exists to close the three W01 final-reentry trust-root blockers found by GitHub Actions run 32512756982.

Development rules:

- `gearbox_clock_epoch_recovery_shadow_v03.py` remains unchanged.
- New implementation must use a new V04 filename and contract.
- Existing passing V03 regression tests remain part of the acceptance baseline.
- The three W01 adversarial failures are release-blocking.
- Formal mission state and prior VERIFIED_PASS evidence are not changed by this candidate work.
- No production key, HSM/TPM, or live routing authority is claimed.

Target blockers:

1. Revalidate current external provider head at final re-entry.
2. Bind ClockEpochRoot trust snapshot to the verified signer trust snapshot.
3. Bind security-relevant clock-key epoch provenance to authenticated checkpoint material, or explicitly downgrade that field to non-security metadata.
