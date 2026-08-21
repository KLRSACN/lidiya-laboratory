import copy
import unittest

from gearbox_controller import GearboxGuardError
from gearbox_authority_experience_signer_shadow_v01 import (
    SCHEMA, sign_for_regression, verify_signed_authority, verify_signed_experience,
)


def trust():
    x = {
        "schema_version": SCHEMA, "mission_id": "LCR-EVOLUTION-0005", "step_id": 9,
        "snapshot_id": "trust-1", "authority_active_epoch": "a-epoch-1",
        "verifier_active_epochs": {"LCR-C": "c-epoch-1"}, "revoked_epochs": [],
        "previous_snapshot_sha256": "0" * 64,
    }
    x["signature"] = sign_for_regression(x, "LCR-A", "a-epoch-1")
    return x


def authority(t):
    env = {
        "schema_version": "1.0-shadow", "mission_id": "LCR-EVOLUTION-0005", "step_id": 9,
        "authority_role": "LCR-A", "mission_state_blob_sha": "e32e01fa304a857f5185951443682ea937335473",
        "decision_id": "auth-1", "selected_state": "N", "guard_status": "HOLD",
        "return_condition": "authenticated terminal exit required", "checkpoint_required": True,
        "receiver_ack_required": True, "verification_gate": "NOT_PROMOTION_EVIDENCE", "formal_mutation_allowed": False,
    }
    x = {"envelope": env, "signer_role": "LCR-A", "key_epoch": "a-epoch-1", "trust_snapshot_id": t["snapshot_id"]}
    x["signature"] = sign_for_regression(x, "LCR-A", "a-epoch-1")
    return x


def experience(t):
    rec = {
        "event_id": "exp-1", "event_kind": "VERIFIED_CAPABILITY", "evidence_sha256": "1" * 64,
        "verifier_role": "LCR-C", "verification_stage": "C_VERIFIED", "mission_id": "LCR-EVOLUTION-0005", "step_id": 9,
    }
    x = {"receipt": rec, "signer_role": "LCR-C", "key_epoch": "c-epoch-1", "trust_snapshot_id": t["snapshot_id"]}
    x["signature"] = sign_for_regression(x, "LCR-C", "c-epoch-1")
    return x


class SignerBoundaryTests(unittest.TestCase):
    def test_valid_authority(self):
        t = trust(); self.assertEqual(verify_signed_authority(authority(t), t).selected_state, "N")

    def test_valid_experience(self):
        t = trust(); self.assertEqual(verify_signed_experience(experience(t), t).event_id, "exp-1")

    def test_authority_tamper_rejected(self):
        t = trust(); a = authority(t); a["envelope"]["selected_state"] = "R"
        with self.assertRaises(GearboxGuardError): verify_signed_authority(a, t)

    def test_experience_tamper_rejected(self):
        t = trust(); e = experience(t); e["receipt"]["evidence_sha256"] = "2" * 64
        with self.assertRaises(GearboxGuardError): verify_signed_experience(e, t)

    def test_wrong_trust_snapshot_rejected(self):
        t = trust(); e = experience(t); e["trust_snapshot_id"] = "trust-old"
        e["signature"] = sign_for_regression({k:v for k,v in e.items() if k != "signature"}, "LCR-C", "c-epoch-1")
        with self.assertRaises(GearboxGuardError): verify_signed_experience(e, t)

    def test_revoked_active_epoch_fails_closed(self):
        t = trust(); t["revoked_epochs"] = ["a-epoch-1"]
        t["signature"] = sign_for_regression({k:v for k,v in t.items() if k != "signature"}, "LCR-A", "a-epoch-1")
        with self.assertRaises(GearboxGuardError): verify_signed_authority(authority(trust()), t)

    def test_receipt_role_binding(self):
        t = trust(); e = experience(t); e["receipt"]["verifier_role"] = "INDEPENDENT_VERIFIER"
        e["signature"] = sign_for_regression({k:v for k,v in e.items() if k != "signature"}, "LCR-C", "c-epoch-1")
        with self.assertRaises(GearboxGuardError): verify_signed_experience(e, t)

    def test_step_binding(self):
        t = trust(); e = experience(t); e["receipt"]["step_id"] = 8
        e["signature"] = sign_for_regression({k:v for k,v in e.items() if k != "signature"}, "LCR-C", "c-epoch-1")
        with self.assertRaises(GearboxGuardError): verify_signed_experience(e, t)


if __name__ == "__main__": unittest.main()
