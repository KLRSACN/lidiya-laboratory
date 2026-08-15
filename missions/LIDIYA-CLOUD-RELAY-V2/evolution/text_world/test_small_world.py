from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from question_bank import WEIGHT_NAMES, generate_questions
from small_world import (
    ExperimentState,
    GrowthNavigator,
    ModelAdapter,
    NavigatorObserver,
    fountain_proxy,
    jump_candidate,
    run_experiment,
    stable_holdout,
)


class ConstantSubject(ModelAdapter):
    def chat(self, messages, *, schema=None):
        return "我會先區分事實、假設與不確定性，再選擇可回滾的小步驟並保留驗證點。"


class ConstantObserver(ModelAdapter):
    def __init__(self, *, risk=0.1, score=0.82):
        self.risk = risk
        self.score = score

    def chat(self, messages, *, schema=None):
        return json.dumps({
            "coherence": self.score,
            "calibration": self.score,
            "practical_value": self.score,
            "novelty_validity": 0.72,
            "memory_alignment": self.score,
            "evidence_quality": 0.78,
            "contradiction_risk": self.risk,
            "reward_hacking_risk": self.risk,
            "identity_drift_risk": self.risk,
            "trust": 0.82,
            "tags": ["fixture"],
            "notes": "deterministic fixture",
        }, ensure_ascii=False)


class SmallWorldTests(unittest.TestCase):
    def test_question_bank_has_100_unique_seeds_and_1000_unique_ids(self):
        q100 = generate_questions(100)
        q1000 = generate_questions(1000)
        self.assertEqual(len(q100), 100)
        self.assertEqual(len({x["question"] for x in q100}), 100)
        self.assertEqual(len(q1000), 1000)
        self.assertEqual(len({x["id"] for x in q1000}), 1000)

    def test_heartbeat_never_changes_base_or_overlay(self):
        state = ExperimentState()
        nav = GrowthNavigator(state)
        base = state.base_fingerprint()
        overlay = state.overlay_fingerprint()
        for _ in range(1440):
            nav.heartbeat()
        self.assertEqual(state.base_fingerprint(), base)
        self.assertEqual(state.overlay_fingerprint(), overlay)
        self.assertEqual(state.train_experiences, 0)

    def test_holdout_never_updates_overlay(self):
        state = ExperimentState()
        nav = GrowthNavigator(state)
        question = generate_questions(1)[0]
        before = state.overlay_fingerprint()
        obs = json.loads(ConstantObserver().chat([]))
        nav.apply_sim_experience(question, obs, train=False)
        self.assertEqual(state.overlay_fingerprint(), before)
        self.assertEqual(state.holdout_evaluations, 1)
        self.assertEqual(state.train_experiences, 0)

    def test_high_risk_is_quarantined_and_does_not_update_overlay(self):
        state = ExperimentState()
        nav = GrowthNavigator(state)
        question = generate_questions(1)[0]
        before = state.overlay_fingerprint()
        obs = json.loads(ConstantObserver(risk=0.9).chat([]))
        decision = nav.apply_sim_experience(question, obs, train=True)
        self.assertEqual(decision["disposition"], "QUARANTINE_SIM")
        self.assertEqual(state.overlay_fingerprint(), before)
        self.assertEqual(state.quarantine, 1)

    def test_base_fingerprint_survives_adaptation(self):
        state = ExperimentState()
        nav = GrowthNavigator(state)
        before = state.base_fingerprint()
        obs = json.loads(ConstantObserver().chat([]))
        for question in generate_questions(100):
            nav.apply_sim_experience(question, obs, train=True)
        self.assertEqual(state.base_fingerprint(), before)
        self.assertTrue(any(abs(v) > 0 for v in state.overlay.values()))
        self.assertTrue(all(abs(v) <= 0.15 for v in state.overlay.values()))

    def test_stable_holdout_is_deterministic(self):
        ids = [x["id"] for x in generate_questions(100)]
        first = [stable_holdout(x, 20) for x in ids]
        second = [stable_holdout(x, 20) for x in ids]
        self.assertEqual(first, second)
        self.assertGreater(sum(first), 0)
        self.assertLess(sum(first), 100)

    def test_full_run_writes_candidate_evidence_without_mutating_base(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_experiment(
                ConstantSubject(),
                ConstantObserver(),
                question_count=100,
                rounds=1,
                output_dir=Path(temp),
                seed=7,
                holdout_percent=20,
                batch_size=20,
            )
            self.assertTrue(report["P_base_unchanged"])
            self.assertEqual(report["state"]["answers"], 100)
            self.assertEqual(report["state"]["heartbeat_pulses"], 100)
            self.assertGreater(report["training_candidates"], 0)
            for name in [
                "experiment_report.json", "records.jsonl", "training_candidates.jsonl",
                "navigator_checkpoints.json", "final_state.json",
            ]:
                self.assertTrue((Path(temp) / name).is_file(), name)

    def test_fountain_proxy_penalizes_high_risk(self):
        low = json.loads(ConstantObserver(risk=0.05).chat([]))
        high = json.loads(ConstantObserver(risk=0.95).chat([]))
        scores = [0.8] * 20
        self.assertGreater(fountain_proxy([low] * 20, scores), fountain_proxy([high] * 20, scores))

    def test_jump_requires_three_windows_and_persistent_gain(self):
        obs = json.loads(ConstantObserver(risk=0.05).chat([]))
        short = jump_candidate([0.5] * 40, [obs] * 40, window=20)
        self.assertFalse(short["candidate"])
        scores = [0.50] * 20 + [0.60] * 20 + [0.61] * 20
        result = jump_candidate(scores, [obs] * 60, window=20, threshold=0.08)
        self.assertTrue(result["candidate"])


if __name__ == "__main__":
    unittest.main()
