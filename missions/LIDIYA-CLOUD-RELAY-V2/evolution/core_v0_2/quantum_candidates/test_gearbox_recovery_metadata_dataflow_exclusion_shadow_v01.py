import unittest

from gearbox_recovery_metadata_dataflow_exclusion_shadow_v01 import (
    LearningProjection, assert_no_metadata_to_learning_path,
    dataflow_boundaries, project_operational_metadata_shadow,
)


class RecoveryMetadataDataflowExclusionTests(unittest.TestCase):
    def test_end_to_end_metadata_is_operational_only(self):
        before = LearningProjection(accepted_experience_ids=("verified-exp-1",), personality=(("warmth", 0.5),))
        metadata = {
            "provider_id": "provider-A", "provider_head_sequence": 91,
            "provider_receipt_hash": "r91", "signer_role": "LCR-A", "signer_epoch": "a-epoch-2",
            "trust_snapshot_id": "trust-2", "key_fingerprint_sha256": "f" * 64,
            "clock_epoch": "clock-2", "clock_sequence": 22, "clock_receipt_hash": "c22",
            "checkpoint_id": "cp-22", "signature_verified": True, "retry_count": 8,
            "backoff_count": 4, "recovery_count": 3, "recovery_duration_ms": 12345,
            "root_reestablishment_count": 2, "secretary_level": "ORANGE",
            "context_load_ratio": 0.9, "tool_failure_ratio": 0.8, "stale_pointer_ratio": 0.7,
            "durable_progress_age_ratio": 0.6, "storage_pressure_ratio": 0.5,
            "continuity_anchor_health": 0.4,
        }
        after = project_operational_metadata_shadow(metadata, learning=before)
        assert_no_metadata_to_learning_path(before, after)
        self.assertEqual(before.bytes_projection(), after.learning.bytes_projection())

    def test_retry_churn_counterfactual_is_learning_identical(self):
        learning = LearningProjection(accepted_experience_ids=("same-verified-exp",), drive=(("goal", 0.7),))
        a = project_operational_metadata_shadow({"retry_count": 0, "recovery_count": 0}, learning=learning)
        b = project_operational_metadata_shadow({"retry_count": 10000, "recovery_count": 999, "root_reestablishment_count": 888}, learning=learning)
        self.assertNotEqual(a.fields, b.fields)
        self.assertEqual(a.learning.bytes_projection(), b.learning.bytes_projection())

    def test_direct_cognitive_sink_injection_fails_closed(self):
        with self.assertRaises(ValueError):
            project_operational_metadata_shadow({"personality": {"avoidance": 1.0}})

    def test_unknown_field_fails_closed(self):
        with self.assertRaises(ValueError):
            project_operational_metadata_shadow({"provider_id": "p", "familiarity_score": 0.9})

    def test_boundary_declares_zero_learning_and_formal_effect(self):
        b = dataflow_boundaries()
        for key in ("experience_delta", "appraisal_delta", "drive_delta", "exploration_delta", "preference_delta", "personality_delta", "trauma_relief_delta", "competence_motivation_delta"):
            self.assertEqual(0, b[key])
        self.assertFalse(b["p_base_mutation"])
        self.assertFalse(b["formal_mutation_allowed"])
        self.assertTrue(b["separate_verified_experience_required_for_learning"])


if __name__ == "__main__": unittest.main()
