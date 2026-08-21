import unittest
from dataclasses import replace

from test_gearbox_clock_epoch_recovery_shadow_v03 import (
    CLOCK_SECRET, MISSION_BLOB, FakeExternalProvider, checkpoint, signed_authority, trust,
)
from gearbox_clock_epoch_recovery_shadow_v04 import (
    ClockEpochRecoveryGuardError, ReentryTrustBinding,
    complete_authenticated_reentry, establish_replacement_clock_epoch,
)
from test_gearbox_clock_epoch_recovery_shadow_v03 import canon_hash


def issue_root_v04(provider, *, trust_id="trust-epoch-2"):
    cp = checkpoint()
    # V04 intentionally preserves the V03 provider-root payload for compatibility;
    # the typed key fingerprint is a mandatory independent re-entry binding.
    payload = {
        "schema_version":"0.3-shadow","mission_id":"LCR-EVOLUTION-0005","step_id":9,
        "epoch_id":"clock-epoch-2","clock_key_epoch":"clock-key-epoch-2","trust_snapshot_id":trust_id,
        "mission_state_blob_sha":MISSION_BLOB,"installation_id":"install-A","runtime_id":"runtime-A",
        "checkpoint_fingerprint":canon_hash(cp.unsigned_binding()),
    }
    receipt = provider.issue(expected_previous_sequence=0, previous_receipt_hash="GENESIS", payload_hash=canon_hash(payload))
    return establish_replacement_clock_epoch(
        provider=provider, provider_receipt=receipt, replacement_checkpoint=cp,
        clock_secret=CLOCK_SECRET, installation_id="install-A", runtime_id="runtime-A",
        epoch_id="clock-epoch-2", clock_key_epoch="clock-key-epoch-2", trust_snapshot_id=trust_id,
        previous_provider_sequence=0, previous_provider_receipt_hash="GENESIS",
        forbidden_local_durability_domain_id="local-clock-domain", mission_state_blob_sha=MISSION_BLOB,
    )


def reenter(provider, root, key_binding, t):
    return complete_authenticated_reentry(
        root=root, key_binding=key_binding, clock_secret=CLOCK_SECRET, provider=provider,
        forbidden_local_durability_domain_id="local-clock-domain",
        signed_authority=signed_authority(t), signer_trust_snapshot=t,
        mission_state_blob_sha=MISSION_BLOB,
    )


class ClockEpochRecoveryShadowV04Tests(unittest.TestCase):
    def test_current_head_matching_snapshot_and_key_reenters(self):
        p=FakeExternalProvider(); root,k,_=issue_root_v04(p); t=trust()
        d=reenter(p,root,k,t)
        self.assertEqual(d.state,"CLOCK_EPOCH_REENTERED_SHADOW")
        self.assertEqual(d.verified_experience_delta,0)

    def test_provider_head_advance_makes_root_stale_even_with_valid_mission_and_signature(self):
        p=FakeExternalProvider(); root,k,_=issue_root_v04(p); t=trust()
        p.issue(expected_previous_sequence=1, previous_receipt_hash=root.provider_receipt.receipt_hash, payload_hash="later")
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError,"provider head advanced"):
            reenter(p,root,k,t)

    def test_trust_snapshot_mismatch_fails_even_with_valid_mission_and_signature(self):
        p=FakeExternalProvider(); root,k,_=issue_root_v04(p,trust_id="other-trust"); t=trust()
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError,"trust snapshot mismatch"):
            reenter(p,root,k,t)

    def test_clock_key_epoch_mismatch_fails_closed(self):
        p=FakeExternalProvider(); root,k,_=issue_root_v04(p); t=trust()
        bad=replace(k,clock_key_epoch="clock-key-epoch-3")
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError,"clock key epoch mismatch"):
            reenter(p,root,bad,t)

    def test_clock_key_fingerprint_mismatch_fails_closed(self):
        p=FakeExternalProvider(); root,k,_=issue_root_v04(p); t=trust()
        bad=replace(k,clock_key_fingerprint_sha256="0"*64)
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError,"clock key fingerprint mismatch"):
            reenter(p,root,bad,t)


if __name__ == "__main__": unittest.main()
