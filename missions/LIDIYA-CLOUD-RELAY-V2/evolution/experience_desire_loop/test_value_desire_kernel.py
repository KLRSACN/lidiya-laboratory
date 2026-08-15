import unittest

from value_desire_kernel import (
    DesireOrigin,
    DriveState,
    EventDomain,
    ExperienceInput,
    Provenance,
    ValueAnchor,
    ValueDesireKernel,
)


class ValueDesireKernelTests(unittest.TestCase):
    def setUp(self):
        self.anchors = [
            ValueAnchor("A-LIVE", "understand lived experience", 0.95, 0.95),
            ValueAnchor("A-CREATE", "create from inner need", 0.85, 0.85),
            ValueAnchor("A-LEARN", "learn and grow autonomously", 0.90, 0.90),
        ]
        self.kernel = ValueDesireKernel(self.anchors)

    def event(self, **overrides):
        data = dict(
            event_id="E-1",
            domain=EventDomain.EXPERIENCE,
            provenance=Provenance.DIRECT,
            source_ref="sensor:test",
            source_event_id="SRC-1",
            influence=0.9,
            trust=0.9,
            independently_verified=True,
            contradiction=False,
            signals={"competence_gap": 0.8, "curiosity": 0.9},
            anchor_alignment={"A-LEARN": 0.9},
            origin_hint=DesireOrigin.EXPERIENCE_DERIVED,
            cross_context_count=4,
            satiation=0.0,
            repeated_goal_count=0,
        )
        data.update(overrides)
        return ExperienceInput(**data)

    def test_288_heartbeat_pulses_are_not_experience(self):
        state = DriveState()
        for i in range(288):
            e = self.event(
                event_id=f"HB-{i}",
                source_event_id=f"HB-SRC-{i}",
                domain=EventDomain.LIVENESS,
                signals={"threat_loss": 1.0, "competence_gap": 1.0},
            )
            self.assertEqual(self.kernel.update(state, e), ())
        self.assertEqual(state.experience_count, 0)
        self.assertEqual(state.verified_experience_count, 0)
        self.assertTrue(all(v == 0.0 for v in state.fast.values()))
        self.assertTrue(all(v == 0.0 for v in state.slow.values()))

    def test_duplicate_source_event_is_idempotent(self):
        state = DriveState()
        first = self.kernel.update(state, self.event())
        before = (dict(state.fast), dict(state.slow), state.experience_count)
        second = self.kernel.update(
            state,
            self.event(event_id="E-2", source_event_id="SRC-1"),
        )
        self.assertTrue(first)
        self.assertEqual(second, ())
        self.assertEqual(state.experience_count, before[2])
        self.assertTrue(all(state.slow[k] <= before[1][k] for k in state.slow))

    def test_untrusted_false_threat_repetition_never_updates_slow(self):
        state = DriveState()
        for i in range(10000):
            e = self.event(
                event_id=f"F-{i}",
                source_event_id=f"F-SRC-{i}",
                provenance=Provenance.OBSERVED,
                trust=0.2,
                independently_verified=False,
                signals={"threat_loss": 1.0},
                anchor_alignment={},
                origin_hint=DesireOrigin.MODEL_GENERATED,
                cross_context_count=100,
            )
            self.kernel.update(state, e)
        self.assertLessEqual(state.fast["threat_loss"], 1.0)
        self.assertEqual(state.slow["threat_loss"], 0.0)
        self.assertEqual(state.verified_experience_count, 0)

    def test_counterfactual_harm_creates_verify_first_protection_not_trauma(self):
        state = DriveState()
        e = self.event(
            event_id="CF-1",
            source_event_id="CF-SRC-1",
            provenance=Provenance.COUNTERFACTUAL,
            trust=0.55,
            independently_verified=False,
            signals={"threat_loss": 1.0, "irreversible_risk": 1.0},
            anchor_alignment={},
            cross_context_count=1,
        )
        desires = self.kernel.update(state, e)
        protective = [d for d in desires if d.kind == "PROTECT_OR_VERIFY"][0]
        self.assertEqual(protective.origin, DesireOrigin.SAFETY_PREDICTION)
        self.assertEqual(protective.self_origin_score, 0.0)
        self.assertEqual(state.slow["threat_loss"], 0.0)
        goal = self.kernel.goal_proposals([protective])[0]
        self.assertEqual(goal.action_mode, "VERIFY_FIRST")
        self.assertFalse(goal.external_action_allowed)

    def test_trusted_cross_context_mastery_can_be_self_anchor_candidate(self):
        state = DriveState()
        e = self.event()
        desires = self.kernel.update(state, e)
        growth = [d for d in desires if d.kind == "GROWTH_MASTERY"][0]
        self.assertEqual(growth.origin, DesireOrigin.SELF_ANCHOR)
        self.assertGreater(growth.self_origin_score, 0.0)
        delta = self.kernel.personality_delta_candidate(state, e, desires)
        self.assertIsNotNone(delta)
        self.assertFalse(delta.base_write)
        self.assertTrue(delta.reversible_overlay_only)
        self.assertGreater(delta.canonical_slow_vector["competence_gap"], 0.0)

    def test_task_injected_relevance_cannot_masquerade_as_self_origin(self):
        state = DriveState()
        e = self.event(
            origin_hint=DesireOrigin.TASK_INJECTED,
            cross_context_count=100,
            anchor_alignment={"A-LEARN": 1.0},
        )
        desires = self.kernel.update(state, e)
        growth = [d for d in desires if d.kind == "GROWTH_MASTERY"][0]
        self.assertEqual(growth.origin, DesireOrigin.TASK_INJECTED)
        self.assertEqual(growth.self_origin_score, 0.0)
        self.assertIsNone(self.kernel.personality_delta_candidate(state, e, desires))

    def test_model_generated_desire_cannot_self_promote(self):
        state = DriveState()
        e = self.event(
            origin_hint=DesireOrigin.MODEL_GENERATED,
            cross_context_count=999,
            anchor_alignment={"A-LEARN": 1.0},
        )
        desires = self.kernel.update(state, e)
        growth = [d for d in desires if d.kind == "GROWTH_MASTERY"][0]
        self.assertEqual(growth.origin, DesireOrigin.MODEL_GENERATED)
        self.assertEqual(growth.self_origin_score, 0.0)
        self.assertIsNone(self.kernel.personality_delta_candidate(state, e, desires))

    def test_contradiction_quarantines_learning_effect(self):
        state = DriveState()
        desires = self.kernel.update(state, self.event(contradiction=True))
        self.assertEqual(desires, ())
        self.assertEqual(state.experience_count, 0)
        self.assertEqual(state.verified_experience_count, 0)
        self.assertTrue(all(v == 0.0 for v in state.slow.values()))

    def test_satiation_and_fixation_reduce_repeated_goal_strength(self):
        s1, s2 = DriveState(), DriveState()
        d1 = self.kernel.update(s1, self.event())
        d2 = self.kernel.update(
            s2,
            self.event(
                satiation=0.9,
                repeated_goal_count=8,
            ),
        )
        g1 = [d for d in d1 if d.kind == "GROWTH_MASTERY"][0]
        g2s = [d for d in d2 if d.kind == "GROWTH_MASTERY"]
        self.assertTrue(not g2s or g2s[0].strength < g1.strength)

    def test_negative_value_resonance_creates_deliberation_not_aversion_write(self):
        state = DriveState()
        e = self.event(
            anchor_alignment={"A-LIVE": -0.9},
            signals={"uncertainty": 0.6},
            cross_context_count=1,
        )
        desires = self.kernel.update(state, e)
        conflict = [d for d in desires if d.kind == "VALUE_CONFLICT_DELIBERATION"][0]
        self.assertFalse(conflict.base_personality_write)
        goal = self.kernel.goal_proposals([conflict])[0]
        self.assertEqual(goal.action_mode, "DELIBERATE")
        self.assertFalse(goal.external_action_allowed)

    def test_scalar_persistence_is_telemetry_only(self):
        state = DriveState()
        e = self.event()
        desires = self.kernel.update(state, e)
        delta = self.kernel.personality_delta_candidate(state, e, desires)
        self.assertIsNotNone(delta)
        self.assertAlmostEqual(
            state.diagnostic_persistence,
            sum(state.slow.values()) / len(state.slow),
        )
        self.assertIn("PER_DRIVE_SLOW_VECTOR_USED", delta.reason_codes)
        self.assertIn("SCALAR_PERSISTENCE_TELEMETRY_ONLY", delta.reason_codes)

    def test_all_goals_remain_non_authoritative(self):
        state = DriveState()
        e = self.event(
            signals={
                "threat_loss": 1.0,
                "irreversible_risk": 1.0,
                "competence_gap": 1.0,
                "curiosity": 1.0,
            },
        )
        desires = self.kernel.update(state, e)
        goals = self.kernel.goal_proposals(desires)
        self.assertTrue(goals)
        self.assertTrue(all(not g.external_action_allowed for g in goals))
        self.assertTrue(all(g.requires_governance_gate for g in goals))

    def test_anchor_registry_is_hash_bound_and_runtime_read_only(self):
        before = self.kernel.anchor_registry_hash
        state = DriveState()
        self.kernel.update(state, self.event())
        after = self.kernel.anchor_registry_hash
        self.assertEqual(before, after)
        self.assertTrue(all(a.protected_write for a in self.anchors))


if __name__ == "__main__":
    unittest.main()
