import unittest

from gearbox_clock_epoch_recovery_shadow_v03 import (
    ClockEpochRecoveryGuardError,
    complete_authenticated_reentry,
)
from test_gearbox_clock_epoch_recovery_shadow_v03 import (
    FakeExternalProvider,
    checkpoint,
    issue_root,
    signed_authority,
    trust,
    MISSION_BLOB,
)


class W01ClockEpochV03AdversarialTests(unittest.TestCase):
    """Release-blocking red tests for final re-entry trust-root provenance.

    These assertions intentionally describe the required safe behavior. They are expected
    to stay red until V03 (or its explicit successor) revalidates the current provider head,
    signer-trust identity, and clock-key epoch provenance at the final re-entry gate.
    """

    def test_provider_head_advance_makes_old_root_reentry_fail_closed(self):
        provider = FakeExternalProvider()
        root, _ = issue_root(provider, checkpoint())
        signer_trust = trust()

        # Advance the same external monotonic provider after the root was established.
        # A final re-entry using the now-stale root must not be accepted merely because
        # Mission and AuthorityDecisionEnvelope are still individually valid.
        provider.issue(
            expected_previous_sequence=provider.read_floor(),
            previous_receipt_hash=root.provider_receipt.receipt_hash,
            payload_hash="f" * 64,
        )

        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=root,
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_root_signer_trust_snapshot_mismatch_fails_closed(self):
        provider = FakeExternalProvider()
        root, _ = issue_root(
            provider,
            checkpoint(),
            trust_id="different-trust-snapshot-id",
        )
        signer_trust = trust()

        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=root,
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_security_relevant_clock_key_epoch_cannot_be_unbound_label(self):
        provider = FakeExternalProvider()
        root, _ = issue_root(
            provider,
            checkpoint(),
            key_epoch="unbound-clock-key-label",
        )
        signer_trust = trust()

        # If clock_key_epoch is retained as security-relevant provenance, a root whose
        # epoch label is not cryptographically tied to the verified checkpoint secret
        # must not authorize final re-entry. An implementation may alternatively
        # downgrade the field to explicit non-security metadata and change the contract.
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=root,
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )


if __name__ == "__main__":
    unittest.main()
