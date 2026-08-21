import unittest

from test_gearbox_clock_epoch_recovery_shadow_v03 import (
    CLOCK_SECRET, MISSION_BLOB, FakeExternalProvider, checkpoint, signed_authority, trust,
)
from test_gearbox_clock_epoch_recovery_shadow_v04 import issue_root_v04, reenter
from gearbox_clock_epoch_recovery_shadow_v04 import ClockEpochRecoveryGuardError
from gearbox_clock_epoch_recovery_shadow_v05 import (
    RecoveryCognitiveState, moving_head_recovery_boundaries, reestablish_current_clock_epoch,
)


def fresh_root(provider, head, suffix):
    return reestablish_current_clock_epoch(
        provider=provider, current_head_receipt=head, replacement_checkpoint=checkpoint(),
        clock_secret=CLOCK_SECRET, installation_id="install-A", runtime_id="runtime-A",
        epoch_id=f"clock-epoch-{suffix}", clock_key_epoch=f"clock-key-epoch-{suffix}",
        trust_snapshot_id="trust-epoch-2", forbidden_local_durability_domain_id="local-clock-domain",
        mission_state_blob_sha=MISSION_BLOB,
    )


class ClockEpochRecoveryShadowV05Tests(unittest.TestCase):
    def test_stable_head_reestablishes_and_reenters(self):
        p=FakeExternalProvider(); root,k,_=fresh_root(p,None,"A"); d=reenter(p,root,k,trust())
        self.assertEqual(d.state,"CLOCK_EPOCH_REENTERED_SHADOW")
        self.assertEqual(d.verified_experience_delta,0)

    def test_moving_provider_head_reestablishment_non_terminal_ab(self):
        cognitive_a=RecoveryCognitiveState(); cognitive_b=RecoveryCognitiveState()

        a=FakeExternalProvider(); root_a,key_a,_=fresh_root(a,None,"A")
        out_a=reenter(a,root_a,key_a,trust())

        b=FakeExternalProvider(); stale1,key1,_=fresh_root(b,None,"B1")
        head2=b.issue(expected_previous_sequence=1, previous_receipt_hash=stale1.provider_receipt.receipt_hash, payload_hash="benign-head-2")
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError,"provider head advanced"):
            reenter(b,stale1,key1,trust())

        stale2,key2,_=fresh_root(b,head2,"B2")
        head4=b.issue(expected_previous_sequence=3, previous_receipt_hash=stale2.provider_receipt.receipt_hash, payload_hash="benign-head-4")
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError,"provider head advanced"):
            reenter(b,stale2,key2,trust())

        root_b,key_b,_=fresh_root(b,head4,"B3")
        out_b=reenter(b,root_b,key_b,trust())
        self.assertEqual(out_b.state,"CLOCK_EPOCH_REENTERED_SHADOW")
        self.assertEqual(out_b.pressure_inputs,out_a.pressure_inputs)
        self.assertFalse(out_b.stale_pressure_carryover)
        self.assertFalse(out_b.prior_terminal_hold_carryover)
        self.assertEqual(cognitive_a,cognitive_b)
        self.assertEqual(cognitive_a.__dict__,cognitive_b.__dict__)

    def test_stale_or_noncurrent_head_receipt_cannot_mint_fresh_root(self):
        p=FakeExternalProvider(); stale,_,_=fresh_root(p,None,"S1")
        head2=p.issue(expected_previous_sequence=1, previous_receipt_hash=stale.provider_receipt.receipt_hash, payload_hash="head2")
        p.issue(expected_previous_sequence=2, previous_receipt_hash=head2.receipt_hash, payload_hash="head3")
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError,"current provider head receipt required"):
            fresh_root(p,head2,"S2")

    def test_churn_is_zero_learning_boundary(self):
        b=moving_head_recovery_boundaries()
        self.assertFalse(b["provider_head_churn_counts_as_experience"])
        self.assertFalse(b["retry_or_backoff_counts_as_experience"])
        self.assertFalse(b["recovery_duration_counts_as_experience"])
        self.assertEqual(b["appraisal_delta"],0)
        self.assertEqual(b["personality_delta"],0)
        self.assertFalse(b["p_base_mutation_allowed"])


if __name__ == "__main__": unittest.main()
