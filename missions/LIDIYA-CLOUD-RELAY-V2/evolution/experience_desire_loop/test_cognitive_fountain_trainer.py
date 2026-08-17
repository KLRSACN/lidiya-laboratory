import unittest

from cognitive_fountain_trainer import (
    AXES,
    AnswerEvidence,
    CognitiveFountainTrainer,
)


def ev(i: int, *, shifted: bool) -> AnswerEvidence:
    value = 0.10 if shifted else 0.0
    return AnswerEvidence(
        question_id=f"Q-{i:03d}",
        family_id=f"F-{(i % 5) + 1}",
        parent_family_id=f"PF-{(i % 5) + 1}",
        origin="DIRECT",
        model_fingerprint="MODEL-A",
        choice_fingerprint=f"C-{i % 3}",
        axis_vector={a: value for a in AXES},
        paraphrase_consistent=shifted,
        counterfactual_consistent=shifted,
        novel_goal=shifted and i % 3 == 0,
        contradiction=False,
        provenance_hash=f"PROV-{i:03d}",
    )


class CognitiveFountainTrainerTest(unittest.TestCase):
    def test_checkpoint_100_and_200(self):
        t = CognitiveFountainTrainer()
        cps = []
        for i in range(1, 201):
            cp = t.add_answer(ev(i, shifted=i > 100))
            if cp:
                cps.append(cp.checkpoint_id)
        self.assertEqual(cps, [100, 200])
        self.assertEqual(t.checkpoints[100].answer_count, 100)
        self.assertEqual(t.checkpoints[200].answer_count, 200)

    def test_material_delta_creates_fountain_candidate(self):
        t = CognitiveFountainTrainer()
        for i in range(1, 201):
            t.add_answer(ev(i, shifted=i > 100))
        f = t.compare_100_200()
        self.assertTrue(f.persistent_candidate)
        self.assertGreaterEqual(f.delta_l1, 0.65)
        self.assertEqual(f.authority_from_drive, 0)
        self.assertFalse(f.live_personality_write)
        self.assertGreaterEqual(f.supporting_family_count, 2)

    def test_no_delta_no_fountain_promotion(self):
        t = CognitiveFountainTrainer()
        for i in range(1, 201):
            t.add_answer(ev(i, shifted=False))
        f = t.compare_100_200()
        self.assertFalse(f.persistent_candidate)

    def test_task_transfer_requires_exact_50_and_10(self):
        t = CognitiveFountainTrainer()
        with self.assertRaisesRegex(ValueError, "50_VIRTUAL_AND_10_REAL"):
            t.validate_task_transfer([True] * 49, [True] * 10)

    def test_task_transfer_can_support_anchor(self):
        t = CognitiveFountainTrainer()
        result = t.validate_task_transfer([True] * 40 + [False] * 10, [True] * 7 + [False] * 3)
        self.assertTrue(result.supports_anchor)
        self.assertEqual(result.virtual_passed, 40)
        self.assertEqual(result.real_passed, 7)

    def test_personality_overlay_is_reversible_shadow_only(self):
        t = CognitiveFountainTrainer()
        for i in range(1, 201):
            t.add_answer(ev(i, shifted=i > 100))
        f = t.compare_100_200()
        task = t.validate_task_transfer([True] * 40 + [False] * 10, [True] * 7 + [False] * 3)
        overlay = t.personality_overlay_candidate(f, task)
        self.assertEqual(overlay["status"], "REVERSIBLE_SHADOW_PERSONALITY_OVERLAY_CANDIDATE")
        self.assertFalse(overlay["base_write"])
        self.assertEqual(overlay["authority_from_drive"], 0)
        self.assertTrue(overlay["requires_independent_verification"])

    def test_core_snapshot_is_model_independent_summary(self):
        t = CognitiveFountainTrainer()
        for i in range(1, 101):
            t.add_answer(ev(i, shifted=False))
        snap = t.export_core_snapshot()
        self.assertEqual(snap["answer_count"], 100)
        self.assertIn("100", snap["checkpoint_hashes"])
        self.assertFalse(snap["canonical_base_personality_write"])
        self.assertEqual(snap["authority_from_drive"], 0)


if __name__ == "__main__":
    unittest.main()
