import unittest

from outcome_prediction_error_closure import (
    AppraisalAcceptanceReceipt,
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

    def receipt(self, source_event_hash="source-event-a", trust_eligibility=True):
        return AppraisalAcceptanceReceipt.build(
            appraisal_id="appraisal-001",
            appraisal_fingerprint="appraisal-fingerprint-a",
            source_event_hash=source_event_hash,
            verifier_envelope_hash="verifier-envelope-a",
            appraisal_policy_hash="appraisal-policy-a",
            anchor_registry_hash="anchor-registry-a",
            trust_eligibility=trust_eligibility,
            acceptance_route="LIVE_SHADOW_APPRAISAL_CHOKE_POINT_V0.1",
        )

    def observation(self, *, provenance="DIRECT", source_event_hash="source-event-a", receipt=None, value=0.70, harm=0.20):
        return Observation(
            observation_id="obs-001",
            goal_id="goal-001",
            observed_value=value,
            observed_harm=harm,
            provenance=provenance,
            source_event_hash=source_event_hash,
            appraisal_receipt=self.receipt(source_event_hash) if receipt is None else receipt,
        )

    def test_exact_direct_appraisal_bound_outcome_closes_with_zero_error(self):
        result = close_outcome(self.pred, self.observation())
        self.assertEqual(result.total_error, 0.0)
        self.assertEqual(result.target_namespace, OutcomeNamespace.AUTOBIOGRAPHICAL)
        self.assertTrue(result.autobiographical_experience_eligible)
        self.assertFalse(result.base_personality_write)
        self.assertEqual(result.external_action_authority, 0)

    def test_more_harm_than_predicted_creates_caution_candidate(self):
        result = close_outcome(self.pred, self.observation(value=0.60, harm=0.80))
        self.assertEqual(result.direction, "INCREASE_CAUTION")
        self.assertGreater(result.planning_delta_candidate, 0.0)

    def test_simulated_outcome_never_becomes_autobiographical(self):
        result = close_outcome(self.pred, self.observation(provenance="SIMULATED", value=0.90, harm=0.00))
        self.assertEqual(result.target_namespace, OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING)
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_missing_appraisal_receipt_stays_planning_only(self):
        obs = Observation("obs-004", "goal-001", 0.80, 0.10, "DIRECT", "source-event-a", None)
        result = close_outcome(self.pred, obs)
        self.assertEqual(result.target_namespace, OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING)
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_ineligible_appraisal_receipt_stays_planning_only(self):
        result = close_outcome(
            self.pred,
            self.observation(receipt=self.receipt(trust_eligibility=False)),
        )
        self.assertEqual(result.target_namespace, OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING)
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_receipt_bound_to_other_source_event_stays_planning_only(self):
        result = close_outcome(
            self.pred,
            self.observation(receipt=self.receipt(source_event_hash="source-event-other")),
        )
        self.assertEqual(result.target_namespace, OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING)
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_tampered_receipt_hash_stays_planning_only(self):
        valid = self.receipt()
        tampered = AppraisalAcceptanceReceipt(
            appraisal_id=valid.appraisal_id,
            appraisal_fingerprint=valid.appraisal_fingerprint,
            source_event_hash=valid.source_event_hash,
            verifier_envelope_hash=valid.verifier_envelope_hash,
            appraisal_policy_hash=valid.appraisal_policy_hash,
            anchor_registry_hash=valid.anchor_registry_hash,
            trust_eligibility=valid.trust_eligibility,
            acceptance_route=valid.acceptance_route,
            receipt_hash="tampered",
        )
        result = close_outcome(self.pred, self.observation(receipt=tampered))
        self.assertEqual(result.target_namespace, OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING)
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_goal_mismatch_fails_closed(self):
        obs = Observation(
            "obs-005",
            "goal-other",
            0.10,
            0.10,
            "DIRECT",
            "source-event-a",
            self.receipt(),
        )
        with self.assertRaisesRegex(ValueError, "GOAL_MISMATCH"):
            close_outcome(self.pred, obs)


if __name__ == "__main__":
    unittest.main()
