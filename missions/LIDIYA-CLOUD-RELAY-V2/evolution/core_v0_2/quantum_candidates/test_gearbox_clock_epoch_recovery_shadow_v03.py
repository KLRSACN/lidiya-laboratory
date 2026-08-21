import hashlib
import json
import unittest

from gearbox_authority_experience_signer_shadow_v01 import SCHEMA as SIGNER_SCHEMA, sign_for_regression
from gearbox_external_monotonic_provider_shadow_v01 import MonotonicReceipt, ProviderBinding
from gearbox_secretary_runtime_freshness_shadow_v02 import ZERO_HASH, sign_clock_checkpoint
from gearbox_clock_epoch_recovery_shadow_v03 import (
    ClockEpochRecoveryGuardError,
    RECOVERY_STATE,
    READY_STATE,
    REENTERED_STATE,
    complete_authenticated_reentry,
    establish_replacement_clock_epoch,
    pressure_history_dataflow_exclusion,
    recovery_boundaries,
    unresolved_chain_break,
)

INSTALL = "install-A"
RUNTIME = "runtime-A"
MISSION_BLOB = "e32e01fa304a857f5185951443682ea937335473"
CLOCK_SECRET = b"quantum-runtime-clock-shadow-key-v01-32bytes"


def canon_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class FakeExternalProvider:
    def __init__(self, *, domain="remote-clock-domain", floor=0):
        self._binding = ProviderBinding("clock-provider-A", domain, INSTALL, RUNTIME)
        self.floor = floor

    def binding(self):
        return self._binding

    def read_floor(self):
        return self.floor

    def issue(self, *, expected_previous_sequence, previous_receipt_hash, payload_hash):
        self.floor = expected_previous_sequence + 1
        return MonotonicReceipt(
            self._binding.provider_id, self._binding.durability_domain_id, INSTALL, RUNTIME,
            self.floor, previous_receipt_hash, payload_hash, f"receipt-{self.floor}", "sig")

    def verify(self, receipt):
        return receipt.signature == "sig"


def checkpoint(seq=0, last_hash=ZERO_HASH, nonce="epoch-cp"):
    return sign_clock_checkpoint({
        "last_clock_seq": seq,
        "last_clock_hash": last_hash,
        "installation_id": INSTALL,
        "runtime_id": RUNTIME,
        "checkpoint_nonce": nonce,
    }, clock_secret=CLOCK_SECRET)


def trust(epoch="a-epoch-2"):
    t = {
        "schema_version": SIGNER_SCHEMA,
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "snapshot_id": "trust-epoch-2",
        "authority_active_epoch": epoch,
        "verifier_active_epochs": {"LCR-C": "c-epoch-2"},
        "revoked_epochs": ["a-epoch-1", "c-epoch-1"],
        "previous_snapshot_sha256": "1" * 64,
    }
    t["signature"] = sign_for_regression(t, "LCR-A", epoch)
    return t


def signed_authority(t):
    env = {
        "schema_version": "1.0-shadow",
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "authority_role": "LCR-A",
        "mission_state_blob_sha": MISSION_BLOB,
        "decision_id": "auth-reentry-1",
        "selected_state": "G2",
        "guard_status": "BRAKE",
        "return_condition": "fresh authority re-evaluation required",
        "checkpoint_required": True,
        "receiver_ack_required": True,
        "verification_gate": "NOT_PROMOTION_EVIDENCE",
        "formal_mutation_allowed": False,
    }
    s = {
        "envelope": env,
        "signer_role": "LCR-A",
        "key_epoch": t["authority_active_epoch"],
        "trust_snapshot_id": t["snapshot_id"],
    }
    s["signature"] = sign_for_regression(s, "LCR-A", s["key_epoch"])
    return s


def issue_root(provider, cp, *, epoch="clock-epoch-2", key_epoch="clock-key-epoch-2", trust_id="trust-epoch-2", prev_seq=0, prev_hash="GENESIS"):
    cp_fingerprint = canon_hash(cp.unsigned_binding())
    payload = {
        "schema_version": "0.3-shadow",
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "epoch_id": epoch,
        "clock_key_epoch": key_epoch,
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


class ClockEpochRecoveryShadowV03Tests(unittest.TestCase):
    def test_chain_break_fails_closed_non_terminal(self):
        d = unresolved_chain_break("checkpoint predecessor mismatch")
        self.assertEqual(d.state, RECOVERY_STATE)
        self.assertFalse(d.routing_authority_allowed)
        self.assertFalse(d.prior_terminal_hold_carryover)
        self.assertFalse(d.stale_pressure_carryover)
        self.assertEqual(d.verified_experience_delta, 0)
        self.assertEqual(d.trauma_or_relief_delta, 0)

    def test_authenticated_replacement_epoch_is_neutral(self):
        root, d = issue_root(FakeExternalProvider(), checkpoint())
        self.assertEqual(root.epoch_id, "clock-epoch-2")
        self.assertEqual(d.state, READY_STATE)
        self.assertEqual(d.secretary_level, "UNKNOWN")
        self.assertTrue(all(v in {0.0, 1.0} for v in d.pressure_inputs.values()))
        self.assertFalse(d.stale_pressure_carryover)
        self.assertFalse(d.prior_terminal_hold_carryover)
        self.assertEqual(d.personality_delta, 0)
        self.assertEqual(d.appraisal_delta, 0)

    def test_provider_floor_rollback_rejected(self):
        p = FakeExternalProvider()
        cp = checkpoint()
        cp_fingerprint = canon_hash(cp.unsigned_binding())
        payload = {
            "schema_version":"0.3-shadow","mission_id":"LCR-EVOLUTION-0005","step_id":9,
            "epoch_id":"clock-epoch-2","clock_key_epoch":"clock-key-epoch-2","trust_snapshot_id":"trust-epoch-2",
            "mission_state_blob_sha":MISSION_BLOB,"installation_id":INSTALL,"runtime_id":RUNTIME,
            "checkpoint_fingerprint":cp_fingerprint,
        }
        r = p.issue(expected_previous_sequence=0, previous_receipt_hash="GENESIS", payload_hash=canon_hash(payload))
        p.floor = 0
        with self.assertRaises(Exception):
            establish_replacement_clock_epoch(
                provider=p, provider_receipt=r, replacement_checkpoint=cp, clock_secret=CLOCK_SECRET,
                installation_id=INSTALL, runtime_id=RUNTIME, epoch_id="clock-epoch-2",
                clock_key_epoch="clock-key-epoch-2", trust_snapshot_id="trust-epoch-2",
                previous_provider_sequence=0, previous_provider_receipt_hash="GENESIS",
                forbidden_local_durability_domain_id="local-clock-domain", mission_state_blob_sha=MISSION_BLOB)

    def test_same_durability_domain_rejected(self):
        p = FakeExternalProvider(domain="local-clock-domain")
        cp = checkpoint()
        cp_fingerprint = canon_hash(cp.unsigned_binding())
        payload = {
            "schema_version":"0.3-shadow","mission_id":"LCR-EVOLUTION-0005","step_id":9,
            "epoch_id":"clock-epoch-2","clock_key_epoch":"clock-key-epoch-2","trust_snapshot_id":"trust-epoch-2",
            "mission_state_blob_sha":MISSION_BLOB,"installation_id":INSTALL,"runtime_id":RUNTIME,
            "checkpoint_fingerprint":cp_fingerprint,
        }
        r = p.issue(expected_previous_sequence=0, previous_receipt_hash="GENESIS", payload_hash=canon_hash(payload))
        with self.assertRaises(Exception):
            establish_replacement_clock_epoch(
                provider=p, provider_receipt=r, replacement_checkpoint=cp, clock_secret=CLOCK_SECRET,
                installation_id=INSTALL, runtime_id=RUNTIME, epoch_id="clock-epoch-2",
                clock_key_epoch="clock-key-epoch-2", trust_snapshot_id="trust-epoch-2",
                previous_provider_sequence=0, previous_provider_receipt_hash="GENESIS",
                forbidden_local_durability_domain_id="local-clock-domain", mission_state_blob_sha=MISSION_BLOB)

    def test_stale_mission_cannot_reenter(self):
        p = FakeExternalProvider(); root, _ = issue_root(p, checkpoint()); t = trust()
        with self.assertRaises(ClockEpochRecoveryGuardError):
            complete_authenticated_reentry(root=root, signed_authority=signed_authority(t), signer_trust_snapshot=t,
                                           mission_state_blob_sha="a" * 40)

    def test_authenticated_reentry_clears_pre_break_pressure_and_terminal_hold(self):
        root, _ = issue_root(FakeExternalProvider(), checkpoint()); t = trust()
        d = complete_authenticated_reentry(root=root, signed_authority=signed_authority(t), signer_trust_snapshot=t,
                                           mission_state_blob_sha=MISSION_BLOB)
        self.assertEqual(d.state, REENTERED_STATE)
        self.assertEqual(d.secretary_level, "UNKNOWN")
        self.assertFalse(d.stale_pressure_carryover)
        self.assertFalse(d.prior_terminal_hold_carryover)
        self.assertEqual(d.verified_experience_delta, 0)
        self.assertEqual(d.personality_delta, 0)
        self.assertEqual(d.trauma_or_relief_delta, 0)

    def test_revoked_or_lost_old_epoch_cannot_authorize_reentry(self):
        root, _ = issue_root(FakeExternalProvider(), checkpoint()); t = trust(); s = signed_authority(t)
        s["key_epoch"] = "a-epoch-1"
        s["signature"] = sign_for_regression({k:v for k,v in s.items() if k != "signature"}, "LCR-A", "a-epoch-1")
        with self.assertRaises(Exception):
            complete_authenticated_reentry(root=root, signed_authority=s, signer_trust_snapshot=t,
                                           mission_state_blob_sha=MISSION_BLOB)

    def test_chronic_pressure_dataflow_has_no_cognitive_sink(self):
        d = pressure_history_dataflow_exclusion()
        forbidden = set(d["forbidden_direct_sinks"])
        self.assertTrue({"Experience","exploration_propensity","personality_candidate","P_base","trauma","relief_reward"} <= forbidden)
        self.assertTrue(d["fresh_neutral_state_resets_pressure_history"])
        self.assertEqual(d["verified_experience_delta"], 0)
        self.assertEqual(d["appraisal_delta"], 0)
        self.assertEqual(d["personality_delta"], 0)

    def test_recovery_boundaries_never_claim_production_or_learning(self):
        b = recovery_boundaries()
        self.assertFalse(b["formal_mutation_allowed"])
        self.assertFalse(b["live_routing_authority_allowed"])
        self.assertFalse(b["recovery_counts_as_experience"])
        self.assertFalse(b["synthetic_provider_or_key_is_production_proof"])


if __name__ == "__main__":
    unittest.main()
