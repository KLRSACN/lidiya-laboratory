import unittest

from activation_gate_guard import (
    GateError,
    claim_gate,
    close_gate,
    evaluate_gate,
    validate_authorization,
)


AUTH = {
    "mission_id": "LCR-AUTONOMY-0002",
    "authorization_type": "ONE_TIME_ACTIVATION_GATE",
    "validation_carrier": {"pull_request": 5, "merge_authorized": False},
    "allowed": {"default_branch_write_scope": [".github/workflows/lcr-cloud-launcher.yml"]},
}


class ActivationGateGuardTests(unittest.TestCase):
    def test_authorization_scope_validates(self):
        validate_authorization(
            AUTH,
            expected_mission="LCR-AUTONOMY-0002",
            launcher_path=".github/workflows/lcr-cloud-launcher.yml",
            validation_pr=5,
        )

    def test_invalid_scope_is_rejected(self):
        with self.assertRaises(GateError):
            validate_authorization(
                AUTH,
                expected_mission="LCR-AUTONOMY-0002",
                launcher_path=".github/workflows/other.yml",
                validation_pr=5,
            )

    def test_fresh_gate_can_be_claimed(self):
        decision = evaluate_gate(None, github_run_id="101")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, "READY_TO_CLAIM")

    def test_other_run_cannot_steal_claim(self):
        ledger = claim_gate(
            mission_id="LCR-AUTONOMY-0002",
            github_run_id="101",
            claimed_at="2026-08-11T10:00:00+00:00",
        )
        decision = evaluate_gate(ledger, github_run_id="202")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "BLOCKED_ACTIVE_CLAIM")

    def test_same_run_can_continue_claim(self):
        ledger = claim_gate(
            mission_id="LCR-AUTONOMY-0002",
            github_run_id="101",
            claimed_at="2026-08-11T10:00:00+00:00",
        )
        decision = evaluate_gate(ledger, github_run_id="101")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, "CLAIMED_BY_THIS_RUN")

    def test_consumed_gate_blocks_replay(self):
        ledger = claim_gate(
            mission_id="LCR-AUTONOMY-0002",
            github_run_id="101",
            claimed_at="2026-08-11T10:00:00+00:00",
        )
        ledger = close_gate(
            ledger,
            github_run_id="101",
            verified_roundtrip=True,
            metabolic_closed=True,
            closure_evidence="artifact://lcr-cloud-roundtrip-evidence",
            closed_at="2026-08-11T10:05:00+00:00",
        )
        self.assertEqual(ledger["status"], "CONSUMED_CLOSED")
        self.assertFalse(ledger["reusable"])
        decision = evaluate_gate(ledger, github_run_id="202")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "BLOCKED_CONSUMED_CLOSED")

    def test_close_requires_verified_roundtrip_and_metabolism(self):
        ledger = claim_gate(
            mission_id="LCR-AUTONOMY-0002",
            github_run_id="101",
            claimed_at="2026-08-11T10:00:00+00:00",
        )
        with self.assertRaises(GateError):
            close_gate(
                ledger,
                github_run_id="101",
                verified_roundtrip=False,
                metabolic_closed=True,
                closure_evidence="artifact://x",
                closed_at="2026-08-11T10:05:00+00:00",
            )
        with self.assertRaises(GateError):
            close_gate(
                ledger,
                github_run_id="101",
                verified_roundtrip=True,
                metabolic_closed=False,
                closure_evidence="artifact://x",
                closed_at="2026-08-11T10:05:00+00:00",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
