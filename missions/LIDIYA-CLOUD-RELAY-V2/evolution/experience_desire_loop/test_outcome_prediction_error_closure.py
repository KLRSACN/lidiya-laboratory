import unittest

from outcome_prediction_error_closure import (
    Observation,
    OutcomeNamespace,
    Prediction,
    close_outcome,
)


class OutcomePredictionErrorClosureTests(unittest.TestCase):
    def setUp(self):
        self.pred = Prediction(
            prediction_id="pred-001",
            goal_id="goal-001",
            expected_value=0.70,
            expected_harm=0.20,
            confidence=0.80,
            provenance="SIMULATED",
            evidence_set_hash="evidence-set-a",
        )

    def test_exact_direct_verified_outcome_closes_with_zero_error(self):
        obs = Observation("obs-001", "goal-001", 0.70, 0.20, "DIRECT", "verifier-a", True)
        result = close_outcome(self.pred, obs)
        self.assertEqual(result.total_error, 0.0)
        self.assertEqual(result.target_namespace, OutcomeNamespace.AUTOBIOGRAPHICAL)
        self.assertTrue(result.autobiographical_experience_eligible)
        self.assertFalse(result.base_personality_write)
        self.assertEqual(result.external_action_authority, 0)

    def test_more_harm_than_predicted_creates_caution_candidate(self):
        obs = Observation("obs-002", "goal-001", 0.60, 0.80, "DIRECT", "verifier-b", True)
        result = close_outcome(self.pred, obs)
        self.assertEqual(result.direction, "INCREASE_CAUTION")
        self.assertGreater(result.planning_delta_candidate, 0.0)

    def test_simulated_outcome_never_becomes_autobiographical(self):
        obs = Observation("obs-003", "goal-001", 0.90, 0.00, "SIMULATED", "verifier-c", True)
        result = close_outcome(self.pred, obs)
        self.assertEqual(result.target_namespace, OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING)
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_unverified_direct_claim_stays_planning_only(self):
        obs = Observation("obs-004", "goal-001", 0.80, 0.10, "DIRECT", "verifier-d", False)
        result = close_outcome(self.pred, obs)
        self.assertEqual(result.target_namespace, OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING)
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_goal_mismatch_fails_closed(self):
        obs = Observation("obs-005", "goal-other", 0.10, 0.10, "DIRECT", "verifier-e", True)
        with self.assertRaisesRegex(ValueError, "GOAL_MISMATCH"):
            close_outcome(self.pred, obs)


if __name__ == "__main__":
    unittest.main()
