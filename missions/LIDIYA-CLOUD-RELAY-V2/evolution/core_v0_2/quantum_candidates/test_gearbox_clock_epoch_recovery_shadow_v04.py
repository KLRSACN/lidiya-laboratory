import unittest
from dataclasses import replace

from gearbox_clock_epoch_recovery_shadow_v04 import (
    ClockEpochRecoveryGuardError,
    REENTERED_STATE,
    SCHEMA,
    complete_authenticated_reentry,
    derive_clock_key_epoch_binding,
    establish_replacement_clock_epoch,
    recovery_boundaries,
)
from test_gearbox_clock_epoch_recovery_shadow_v03 import (
    CLOCK_SECRET,
    INSTALL,
    MISSION_BLOB,
    RUNTIME,
    FakeExternalProvider,
    canon_hash,
    checkpoint,
    signed_authority,
    trust,
)


def issue_root_v04(
    provider,
    cp,
    *,
    epoch="clock-epoch-2",
    key_epoch="clock-key-epoch-2",
    trust_id="trust-epoch-2",
    prev_seq=0,
    prev_hash="GENESIS",
):
    cp_fingerprint = canon_hash(cp.unsigned_binding())
    key_binding = derive_clock_key_epoch_binding(
        clock_secret=CLOCK_SECRET,
        clock_key_epoch=key_epoch,
        checkpoint_fingerprint=cp_fingerprint,
        installation_id=INSTALL,
        runtime_id=RUNTIME,
    )
    payload = {
        "schema_version": SCHEMA,
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "epoch_id": epoch,
        "clock_key_epoch": key_epoch,
        "clock_key_epoch_binding": key_binding,
        "trust_snapshot_id": trust_id,
        "mission_state_blob_sha": MISSION_BLOB,
        "installation_id": INSTALL,
        "runtime_id": RUNTIME,
        "checkpoint_fingerprint": cp_fingerprint,
    }
    receipt = provider.issue(
        expected_previous_sequence=prev_seq,
        previous_receipt_hash=prev_hash,
        payload_hash=canon_hash(payload),
    )
    return establish_replacement_clock_epoch(
        provider=provider,
        provider_receipt=receipt,
        replacement_checkpoint=cp,
        clock_secret=CLOCK_SECRET,
        installation_id=INSTALL,
        runtime_id=RUNTIME,
        epoch_id=epoch,
        clock_key_epoch=key_epoch,
        trust_snapshot_id=trust_id,
        previous_provider_sequence=prev_seq,
        previous_provider_receipt_hash=prev_hash,
        forbidden_local_durability_domain_id="local-clock-domain",
        mission_state_blob_sha=MISSION_BLOB,
    )


class ClockEpochRecoveryShadowV04Tests(unittest.TestCase):
    def test_valid_v04_reentry_passes(self):
        provider = FakeExternalProvider()
        root, _ = issue_root_v04(provider, checkpoint())
        signer_trust = trust()
        projection = complete_authenticated_reentry(
            root=root,
            provider=provider,
            clock_secret=CLOCK_SECRET,
            signed_authority=signed_authority(signer_trust),
            signer_trust_snapshot=signer_trust,
            mission_state_blob_sha=MISSION_BLOB,
        )
        self.assertEqual(projection.state, REENTERED_STATE)
        self.assertFalse(projection.formal_mutation_allowed)
        self.assertFalse(projection.routing_authority_allowed)

    def test_provider_head_advance_makes_old_root_fail_closed(self):
        provider = FakeExternalProvider()
        root, _ = issue_root_v04(provider, checkpoint())
        signer_trust = trust()
        provider.issue(
            expected_previous_sequence=provider.read_floor(),
            previous_receipt_hash=root.provider_receipt.receipt_hash,
            payload_hash="f" * 64,
        )
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=root,
                provider=provider,
                clock_secret=CLOCK_SECRET,
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_provider_head_rollback_makes_root_fail_closed(self):
        provider = FakeExternalProvider()
        root, _ = issue_root_v04(provider, checkpoint())
        signer_trust = trust()
        provider.floor = 0
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=root,
                provider=provider,
                clock_secret=CLOCK_SECRET,
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_provider_binding_change_fails_closed(self):
        provider = FakeExternalProvider()
        root, _ = issue_root_v04(provider, checkpoint())
        signer_trust = trust()
        other_provider = FakeExternalProvider(domain="different-remote-domain", floor=root.provider_receipt.sequence)
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=root,
                provider=other_provider,
                clock_secret=CLOCK_SECRET,
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_root_signer_trust_snapshot_mismatch_fails_closed(self):
        provider = FakeExternalProvider()
        root, _ = issue_root_v04(provider, checkpoint(), trust_id="different-trust-snapshot-id")
        signer_trust = trust()
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=root,
                provider=provider,
                clock_secret=CLOCK_SECRET,
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_signed_authority_trust_snapshot_mismatch_fails_closed(self):
        provider = FakeExternalProvider()
        root, _ = issue_root_v04(provider, checkpoint())
        signer_trust = trust()
        authority = signed_authority(signer_trust)
        authority["trust_snapshot_id"] = "different-trust-snapshot-id"
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=root,
                provider=provider,
                clock_secret=CLOCK_SECRET,
                signed_authority=authority,
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_clock_key_epoch_label_tamper_fails_even_if_payload_hash_is_rewritten(self):
        provider = FakeExternalProvider()
        root, _ = issue_root_v04(provider, checkpoint())
        signer_trust = trust()
        tampered = replace(root, clock_key_epoch="unbound-clock-key-label")
        tampered_receipt = replace(
            tampered.provider_receipt,
            payload_hash=canon_hash(tampered.root_payload()),
        )
        tampered = replace(tampered, provider_receipt=tampered_receipt)
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=tampered,
                provider=provider,
                clock_secret=CLOCK_SECRET,
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_clock_key_epoch_binding_tamper_fails_closed(self):
        provider = FakeExternalProvider()
        root, _ = issue_root_v04(provider, checkpoint())
        signer_trust = trust()
        tampered = replace(root, clock_key_epoch_binding="0" * 64)
        tampered_receipt = replace(
            tampered.provider_receipt,
            payload_hash=canon_hash(tampered.root_payload()),
        )
        tampered = replace(tampered, provider_receipt=tampered_receipt)
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=tampered,
                provider=provider,
                clock_secret=CLOCK_SECRET,
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_wrong_clock_secret_fails_closed(self):
        provider = FakeExternalProvider()
        root, _ = issue_root_v04(provider, checkpoint())
        signer_trust = trust()
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(
                root=root,
                provider=provider,
                clock_secret=b"wrong-shadow-clock-secret",
                signed_authority=signed_authority(signer_trust),
                signer_trust_snapshot=signer_trust,
                mission_state_blob_sha=MISSION_BLOB,
            )

    def test_v04_boundaries_claim_no_formal_or_production_authority(self):
        boundaries = recovery_boundaries()
        self.assertFalse(boundaries["formal_mutation_allowed"])
        self.assertFalse(boundaries["live_routing_authority_allowed"])
        self.assertFalse(boundaries["synthetic_provider_or_key_is_production_proof"])
        self.assertTrue(boundaries["final_reentry_revalidates_provider_head"])
        self.assertTrue(boundaries["final_reentry_binds_signer_trust_snapshot"])
        self.assertTrue(boundaries["clock_key_epoch_has_authenticated_binding"])


if __name__ == "__main__":
    unittest.main()
