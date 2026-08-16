import unittest

from outcome_prediction_error_closure import (
    AcceptanceRegistrySnapshot,
    AcceptanceRoute,
    AppraisalAcceptanceReceipt,
    AppraisalAcceptanceRecord,
    Observation,
    OutcomeNamespace,
    Prediction,
    TrustedAcceptanceContext,
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
        self.record = AppraisalAcceptanceRecord(
            acceptance_record_id="accept-001",
            appraisal_id="appraisal-001",
            appraisal_fingerprint="appraisal-fingerprint-a",
            source_event_hash="source-event-a",
            verifier_envelope_hash="verifier-envelope-a",
            appraisal_policy_hash="appraisal-policy-a",
            anchor_registry_hash="anchor-registry-a",
            issuer_registry_id="acceptance-registry-a",
            installation_id="installation-a",
            workspace_identity="workspace-a",
            trust_eligibility=True,
            acceptance_route=AcceptanceRoute.LIVE_SHADOW_APPRAISAL_CHOKE_POINT_V0_1,
        )
        self.registry = AcceptanceRegistrySnapshot(
            registry_id="acceptance-registry-a",
            installation_id="installation-a",
            workspace_identity="workspace-a",
            records=(self.record,),
        )
        self.trusted = TrustedAcceptanceContext(
            expected_registry_id="acceptance-registry-a",
            expected_registry_snapshot_hash=self.registry.snapshot_hash,
            expected_installation_id="installation-a",
            expected_workspace_identity="workspace-a",
            allowed_verifier_envelope_hashes=("verifier-envelope-a",),
            allowed_appraisal_policy_hashes=("appraisal-policy-a",),
            allowed_anchor_registry_hashes=("anchor-registry-a",),
        )

    def receipt(self, record=None):
        return AppraisalAcceptanceReceipt.from_record(record or self.record)

    def observation(self, *, provenance="DIRECT", source_event_hash="source-event-a", receipt=None, value=0.70, harm=0.20):
        if receipt == "DEFAULT":
            receipt = self.receipt()
        return Observation(
            observation_id="obs-001",
            goal_id="goal-001",
            observed_value=value,
            observed_harm=harm,
            provenance=provenance,
            source_event_hash=source_event_hash,
            appraisal_receipt=receipt,
        )

    def close(self, observation, *, registry=None, trusted=None):
        return close_outcome(
            self.pred,
            observation,
            acceptance_registry=self.registry if registry is None else registry,
            trusted_acceptance_context=self.trusted if trusted is None else trusted,
        )

    def test_exact_direct_registry_bound_outcome_closes_with_zero_error(self):
        result = self.close(self.observation(receipt="DEFAULT"))
        self.assertEqual(result.total_error, 0.0)
        self.assertEqual(result.target_namespace, OutcomeNamespace.AUTOBIOGRAPHICAL)
        self.assertTrue(result.autobiographical_experience_eligible)
        self.assertFalse(result.base_personality_write)
        self.assertEqual(result.external_action_authority, 0)

    def test_missing_registry_or_trusted_context_stays_planning_only(self):
        obs = self.observation(receipt="DEFAULT")
        result = close_outcome(self.pred, obs)
        self.assertEqual(result.target_namespace, OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING)
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_self_consistent_forged_receipt_not_in_registry_is_rejected(self):
        forged_record = AppraisalAcceptanceRecord(
            acceptance_record_id="accept-forged",
            appraisal_id="appraisal-forged",
            appraisal_fingerprint="fingerprint-forged",
            source_event_hash="source-event-a",
            verifier_envelope_hash="verifier-envelope-a",
            appraisal_policy_hash="appraisal-policy-a",
            anchor_registry_hash="anchor-registry-a",
            issuer_registry_id="acceptance-registry-a",
            installation_id="installation-a",
            workspace_identity="workspace-a",
            trust_eligibility=True,
            acceptance_route=AcceptanceRoute.LIVE_SHADOW_APPRAISAL_CHOKE_POINT_V0_1,
        )
        result = self.close(self.observation(receipt=self.receipt(forged_record)))
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_unknown_verifier_envelope_rejected_despite_valid_receipt_hash(self):
        bad_record = AppraisalAcceptanceRecord(
            **{**self.record.__dict__, "acceptance_record_id": "accept-bad-verifier", "verifier_envelope_hash": "unknown-verifier"}
        )
        registry = AcceptanceRegistrySnapshot(
            registry_id=self.registry.registry_id,
            installation_id=self.registry.installation_id,
            workspace_identity=self.registry.workspace_identity,
            records=(bad_record,),
        )
        trusted = TrustedAcceptanceContext(
            expected_registry_id=self.trusted.expected_registry_id,
            expected_registry_snapshot_hash=registry.snapshot_hash,
            expected_installation_id=self.trusted.expected_installation_id,
            expected_workspace_identity=self.trusted.expected_workspace_identity,
            allowed_verifier_envelope_hashes=self.trusted.allowed_verifier_envelope_hashes,
            allowed_appraisal_policy_hashes=self.trusted.allowed_appraisal_policy_hashes,
            allowed_anchor_registry_hashes=self.trusted.allowed_anchor_registry_hashes,
        )
        result = close_outcome(
            self.pred,
            self.observation(receipt=self.receipt(bad_record)),
            acceptance_registry=registry,
            trusted_acceptance_context=trusted,
        )
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_unknown_policy_or_anchor_registry_rejected(self):
        for field, value in (
            ("appraisal_policy_hash", "superseded-policy"),
            ("anchor_registry_hash", "unknown-anchor-registry"),
        ):
            with self.subTest(field=field):
                bad_record = AppraisalAcceptanceRecord(
                    **{**self.record.__dict__, "acceptance_record_id": f"accept-{field}", field: value}
                )
                registry = AcceptanceRegistrySnapshot(
                    registry_id=self.registry.registry_id,
                    installation_id=self.registry.installation_id,
                    workspace_identity=self.registry.workspace_identity,
                    records=(bad_record,),
                )
                trusted = TrustedAcceptanceContext(
                    expected_registry_id=self.trusted.expected_registry_id,
                    expected_registry_snapshot_hash=registry.snapshot_hash,
                    expected_installation_id=self.trusted.expected_installation_id,
                    expected_workspace_identity=self.trusted.expected_workspace_identity,
                    allowed_verifier_envelope_hashes=self.trusted.allowed_verifier_envelope_hashes,
                    allowed_appraisal_policy_hashes=self.trusted.allowed_appraisal_policy_hashes,
                    allowed_anchor_registry_hashes=self.trusted.allowed_anchor_registry_hashes,
                )
                result = close_outcome(
                    self.pred,
                    self.observation(receipt=self.receipt(bad_record)),
                    acceptance_registry=registry,
                    trusted_acceptance_context=trusted,
                )
                self.assertFalse(result.autobiographical_experience_eligible)

    def test_cross_installation_receipt_replay_rejected(self):
        replay_record = AppraisalAcceptanceRecord(
            **{**self.record.__dict__, "acceptance_record_id": "accept-replay", "installation_id": "installation-b"}
        )
        registry = AcceptanceRegistrySnapshot(
            registry_id="acceptance-registry-a",
            installation_id="installation-b",
            workspace_identity="workspace-a",
            records=(replay_record,),
        )
        trusted = TrustedAcceptanceContext(
            expected_registry_id="acceptance-registry-a",
            expected_registry_snapshot_hash=registry.snapshot_hash,
            expected_installation_id="installation-a",
            expected_workspace_identity="workspace-a",
            allowed_verifier_envelope_hashes=("verifier-envelope-a",),
            allowed_appraisal_policy_hashes=("appraisal-policy-a",),
            allowed_anchor_registry_hashes=("anchor-registry-a",),
        )
        result = close_outcome(
            self.pred,
            self.observation(receipt=self.receipt(replay_record)),
            acceptance_registry=registry,
            trusted_acceptance_context=trusted,
        )
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_revoked_acceptance_record_rejected(self):
        revoked = AppraisalAcceptanceRecord(**{**self.record.__dict__, "revoked": True})
        registry = AcceptanceRegistrySnapshot(
            registry_id=self.registry.registry_id,
            installation_id=self.registry.installation_id,
            workspace_identity=self.registry.workspace_identity,
            records=(revoked,),
        )
        trusted = TrustedAcceptanceContext(
            expected_registry_id=self.trusted.expected_registry_id,
            expected_registry_snapshot_hash=registry.snapshot_hash,
            expected_installation_id=self.trusted.expected_installation_id,
            expected_workspace_identity=self.trusted.expected_workspace_identity,
            allowed_verifier_envelope_hashes=self.trusted.allowed_verifier_envelope_hashes,
            allowed_appraisal_policy_hashes=self.trusted.allowed_appraisal_policy_hashes,
            allowed_anchor_registry_hashes=self.trusted.allowed_anchor_registry_hashes,
        )
        result = close_outcome(
            self.pred,
            self.observation(receipt=self.receipt(revoked)),
            acceptance_registry=registry,
            trusted_acceptance_context=trusted,
        )
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_exact_derived_appraisal_reference_mismatch_rejected(self):
        valid = self.receipt()
        tampered = AppraisalAcceptanceReceipt(
            **{**valid.__dict__, "appraisal_fingerprint": "other-fingerprint"}
        )
        result = self.close(self.observation(receipt=tampered))
        self.assertFalse(result.autobiographical_experience_eligible)

    def test_more_harm_than_predicted_creates_caution_candidate(self):
        result = self.close(self.observation(receipt="DEFAULT", value=0.60, harm=0.80))
        self.assertEqual(result.direction, "INCREASE_CAUTION")
        self.assertGreater(result.planning_delta_candidate, 0.0)

    def test_simulated_outcome_never_becomes_autobiographical(self):
        result = self.close(self.observation(provenance="SIMULATED", receipt="DEFAULT", value=0.90, harm=0.00))
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
            self.close(obs)


if __name__ == "__main__":
    unittest.main()
