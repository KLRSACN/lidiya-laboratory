import copy
import hashlib
import json
import unittest

from gearbox_authority_experience_signer_shadow_v01 import SCHEMA, sign_for_regression
from gearbox_external_monotonic_provider_shadow_v01 import MonotonicReceipt, ProviderBinding
from gearbox_signer_epoch_recovery_shadow_v01 import (
    SignerEpochRecoveryGuardError,
    bootstrap_trust_root,
    complete_shadow_reentry,
    recover_new_epoch,
    recovery_boundaries,
)

MISSION_BLOB = "e32e01fa304a857f5185951443682ea937335473"


def canon_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def trust1():
    x = {
        "schema_version": SCHEMA,
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "snapshot_id": "trust-1",
        "authority_active_epoch": "a-epoch-1",
        "verifier_active_epochs": {"LCR-C": "c-epoch-1"},
        "revoked_epochs": [],
        "previous_snapshot_sha256": "0" * 64,
    }
    x["signature"] = sign_for_regression(x, "LCR-A", "a-epoch-1")
    return x


def trust2(previous):
    x = {
        "schema_version": SCHEMA,
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "snapshot_id": "trust-2",
        "authority_active_epoch": "a-epoch-2",
        "verifier_active_epochs": {"LCR-C": "c-epoch-2"},
        "revoked_epochs": ["a-epoch-1", "c-epoch-1"],
        "previous_snapshot_sha256": canon_hash(previous),
    }
    x["signature"] = sign_for_regression(x, "LCR-A", "a-epoch-2")
    return x


def fresh_authority(t):
    env = {
        "schema_version": "1.0-shadow",
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "authority_role": "LCR-A",
        "mission_state_blob_sha": MISSION_BLOB,
        "decision_id": "fresh-auth-2",
        "selected_state": "G3",
        "guard_status": "CLEAR",
        "return_condition": "downshift on verified risk",
        "checkpoint_required": True,
        "receiver_ack_required": True,
        "verification_gate": "NOT_PROMOTION_EVIDENCE",
        "formal_mutation_allowed": False,
    }
    x = {
        "envelope": env,
        "signer_role": "LCR-A",
        "key_epoch": "a-epoch-2",
        "trust_snapshot_id": t["snapshot_id"],
    }
    x["signature"] = sign_for_regression(x, "LCR-A", "a-epoch-2")
    return x


class FakeExternalProvider:
    def __init__(self, domain="remote-trust-domain"):
        self._binding = ProviderBinding("provider-A", domain, "inst-A", "run-A")
        self.floor = 0
        self.last_receipt_hash = "GENESIS"

    def binding(self):
        return self._binding

    def read_floor(self):
        return self.floor

    def issue(self, *, expected_previous_sequence, previous_receipt_hash, payload_hash):
        if expected_previous_sequence != self.floor:
            raise ValueError("provider expected sequence mismatch")
        if previous_receipt_hash != self.last_receipt_hash:
            raise ValueError("provider predecessor mismatch")
        self.floor += 1
        receipt_hash = hashlib.sha256(f"{self.floor}|{previous_receipt_hash}|{payload_hash}".encode()).hexdigest()
        self.last_receipt_hash = receipt_hash
        return MonotonicReceipt(
            "provider-A", self._binding.durability_domain_id,
            self._binding.installation_id, self._binding.runtime_id,
            self.floor, previous_receipt_hash, payload_hash, receipt_hash, "valid",
        )

    def verify(self, receipt):
        return receipt.signature == "valid"


class SignerEpochRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeExternalProvider()
        self.old = trust1()
        self.root = bootstrap_trust_root(
            trust_snapshot=self.old,
            provider=self.provider,
            installation_id="inst-A",
            runtime_id="run-A",
            local_durability_domain_id="local-domain",
        )

    def recover(self):
        new = trust2(self.old)
        recovered = recover_new_epoch(
            current_root=self.root,
            replacement_trust_snapshot=new,
            provider=self.provider,
            fresh_mission_state_blob_sha=MISSION_BLOB,
        )
        return new, recovered

    def test_authenticated_new_epoch_is_non_terminal_and_neutral(self):
        new, recovered = self.recover()
        self.assertEqual(recovered.state, "AUTHENTICATED_NEW_EPOCH_RECOVERED_AWAITING_FRESH_AUTHORITY")
        self.assertEqual(recovered.secretary_level, "UNKNOWN")
        self.assertFalse(recovered.stale_pressure_carryover_allowed)
        self.assertFalse(recovered.terminal_hold_carryover_allowed)
        self.assertEqual(recovered.experience_delta, 0)
        self.assertFalse(recovered.live_routing_authority_allowed)
        self.assertEqual(new["authority_active_epoch"], "a-epoch-2")

    def test_fresh_authority_reentry_does_not_revive_old_terminal_or_pressure_state(self):
        new, recovered = self.recover()
        result = complete_shadow_reentry(
            recovered_root=recovered,
            provider=self.provider,
            signed_authority=fresh_authority(new),
        )
        self.assertEqual(result.selected_state, "G3")
        self.assertEqual(result.secretary_level, "UNKNOWN")
        self.assertTrue(all(value == 0.0 for value in result.pressure_inputs.values()))
        self.assertFalse(result.stale_pressure_carryover_allowed)
        self.assertFalse(result.terminal_hold_carryover_allowed)
        self.assertEqual(result.experience_delta, 0)
        self.assertFalse(result.live_routing_authority_allowed)

    def test_local_trust_root_rollback_after_recovery_is_detected_by_external_floor(self):
        self.recover()
        with self.assertRaisesRegex(SignerEpochRecoveryGuardError, "TRUST_ROOT_ROLLBACK"):
            complete_shadow_reentry(
                recovered_root=self.root,
                provider=self.provider,
                signed_authority=fresh_authority(trust2(self.old)),
            )

    def test_replacement_must_link_exact_previous_snapshot_hash(self):
        new = trust2(self.old)
        new["previous_snapshot_sha256"] = "f" * 64
        new["signature"] = sign_for_regression({k: v for k, v in new.items() if k != "signature"}, "LCR-A", "a-epoch-2")
        with self.assertRaisesRegex(SignerEpochRecoveryGuardError, "PREDECESSOR"):
            recover_new_epoch(current_root=self.root, replacement_trust_snapshot=new,
                              provider=self.provider, fresh_mission_state_blob_sha=MISSION_BLOB)

    def test_old_authority_and_verifier_epochs_must_be_revoked(self):
        new = trust2(self.old)
        new["revoked_epochs"] = []
        new["signature"] = sign_for_regression({k: v for k, v in new.items() if k != "signature"}, "LCR-A", "a-epoch-2")
        with self.assertRaisesRegex(SignerEpochRecoveryGuardError, "OLD_AUTHORITY_EPOCH"):
            recover_new_epoch(current_root=self.root, replacement_trust_snapshot=new,
                              provider=self.provider, fresh_mission_state_blob_sha=MISSION_BLOB)

    def test_same_durability_domain_provider_is_rejected(self):
        provider = FakeExternalProvider(domain="local-domain")
        with self.assertRaises(SignerEpochRecoveryGuardError):
            bootstrap_trust_root(trust_snapshot=self.old, provider=provider,
                                 installation_id="inst-A", runtime_id="run-A",
                                 local_durability_domain_id="local-domain")

    def test_recovery_replay_from_old_root_cannot_mint_another_epoch(self):
        self.recover()
        with self.assertRaisesRegex(SignerEpochRecoveryGuardError, "TRUST_ROOT_ROLLBACK"):
            recover_new_epoch(current_root=self.root, replacement_trust_snapshot=trust2(self.old),
                              provider=self.provider, fresh_mission_state_blob_sha=MISSION_BLOB)

    def test_boundary_flags_are_zero_learning_and_non_live(self):
        b = recovery_boundaries()
        self.assertFalse(b["formal_mutation_allowed"])
        self.assertFalse(b["live_routing_authority_allowed"])
        self.assertFalse(b["recovery_counts_as_experience"])
        self.assertFalse(b["recovery_counts_as_operational_progress"])
        self.assertFalse(b["stale_pressure_carryover_allowed"])
        self.assertFalse(b["terminal_hold_carryover_allowed"])
        self.assertFalse(b["real_external_provider_installed"])


if __name__ == "__main__":
    unittest.main()
