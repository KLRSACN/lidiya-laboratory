import unittest

from semantic_goal_canonicalizer import SemanticGoalCanonicalizer


class GoalSurfacingContradictionTypeVetoTests(unittest.TestCase):
    def _candidate(self):
        canonicalizer = SemanticGoalCanonicalizer()
        candidate = canonicalizer.canonicalize("g-1", "review bounded goal", ["lineage-1"])
        self.assertTrue(canonicalizer.admit_once(candidate))
        return canonicalizer, candidate

    @staticmethod
    def _kwargs(contradiction_clear):
        return {
            "appraisal_evidence_hashes": ["appraisal-1"],
            "contradiction_scan_hash": "scan-1",
            "contradiction_clear": contradiction_clear,
            "expected_benefit_ref": "benefit-1",
            "expected_cost_ref": "cost-1",
            "expected_risk_ref": "risk-1",
            "protected_object_impact_ref": "protected-impact-1",
            "why_now": "new-material-event",
            "uncertainty_ref": "uncertainty-1",
            "ecology_policy_hash": "policy-TEST_REQUIRED",
            "ecology_cycle_id": "cycle-1",
        }

    def test_literal_false_remains_blocked(self):
        canonicalizer, candidate = self._candidate()
        with self.assertRaises(ValueError):
            canonicalizer.build_surfacing_envelope(candidate, **self._kwargs(False))

    def test_string_false_cannot_truthiness_bypass_gate(self):
        canonicalizer, candidate = self._candidate()
        with self.assertRaisesRegex(ValueError, "NON_BOOLEAN_CONTRADICTION_CLEAR"):
            canonicalizer.build_surfacing_envelope(candidate, **self._kwargs("false"))

    def test_truthy_non_boolean_values_cannot_bypass_gate(self):
        for value in (1, ["clear"], {"clear": True}, object()):
            with self.subTest(value_type=type(value).__name__):
                canonicalizer, candidate = self._candidate()
                with self.assertRaisesRegex(ValueError, "NON_BOOLEAN_CONTRADICTION_CLEAR"):
                    canonicalizer.build_surfacing_envelope(candidate, **self._kwargs(value))

    def test_literal_true_is_proposal_only(self):
        canonicalizer, candidate = self._candidate()
        envelope = canonicalizer.build_surfacing_envelope(candidate, **self._kwargs(True))
        self.assertIs(envelope.contradiction_clear, True)
        self.assertEqual(envelope.authority_from_drive, 0)
        self.assertFalse(envelope.external_action_allowed)
        self.assertFalse(envelope.canonical_personality_write)


if __name__ == "__main__":
    unittest.main()
