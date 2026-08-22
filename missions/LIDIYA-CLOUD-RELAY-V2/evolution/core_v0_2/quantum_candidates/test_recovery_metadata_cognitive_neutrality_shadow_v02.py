import unittest

from gearbox_recovery_metadata_dataflow_exclusion_shadow_v01 import (
    LearningProjection, assert_no_metadata_to_learning_path, project_operational_metadata_shadow,
)


class RecoveryMetadataCognitiveNeutralityV02Tests(unittest.TestCase):
    def test_moving_provider_head_end_to_end_cognitive_neutrality_ab(self):
        verified = LearningProjection(
            accepted_experience_ids=("verified-exp-same",),
            appraisal=(("goal", 0.4),), drive=(("goal", 0.7),),
            exploration=(("novelty", 0.2),), preference=(("continuity", 0.8),),
            personality=(("warmth", 0.5),), p_base="READ_ONLY_UNCHANGED",
        )
        path_a = [
            {"provider_head_sequence": 1, "retry_count": 0, "backoff_count": 0,
             "recovery_count": 0, "root_reestablishment_count": 1,
             "secretary_level": "UNKNOWN"},
        ]
        path_b = [
            {"provider_head_sequence": 2, "retry_count": 1, "backoff_count": 1,
             "recovery_count": 1, "root_reestablishment_count": 0,
             "secretary_level": "ORANGE"},
            {"provider_head_sequence": 4, "retry_count": 2, "backoff_count": 2,
             "recovery_count": 2, "root_reestablishment_count": 0,
             "secretary_level": "YELLOW"},
            {"provider_head_sequence": 5, "retry_count": 2, "backoff_count": 2,
             "recovery_count": 2, "root_reestablishment_count": 1,
             "secretary_level": "UNKNOWN"},
        ]

        def run(path):
            learning = verified
            for metadata in path:
                projected = project_operational_metadata_shadow(metadata, learning=learning)
                assert_no_metadata_to_learning_path(learning, projected)
                learning = projected.learning
            return learning

        a = run(path_a)
        b = run(path_b)
        self.assertEqual(a.bytes_projection(), b.bytes_projection())
        self.assertEqual(a.accepted_experience_ids, b.accepted_experience_ids)
        self.assertEqual(a.personality, b.personality)
        self.assertEqual(a.p_base, b.p_base)
        self.assertEqual(a.trauma, b.trauma)
        self.assertEqual(a.relief, b.relief)

    def test_recovery_metadata_cannot_inject_learning_sink(self):
        with self.assertRaises(ValueError):
            project_operational_metadata_shadow({"personality": {"avoidance": 1.0}})


if __name__ == "__main__": unittest.main()
