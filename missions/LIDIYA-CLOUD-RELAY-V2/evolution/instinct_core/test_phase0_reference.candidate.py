import unittest
from phase0_reference import Phase0InstinctCore, Phase0State, DriveObservation, N


def obs(**changes):
    base = dict(
        signals=[0.0]*N,
        memory_influence=[0.0]*N,
        trust=[0.0]*N,
        repetition=[0]*N,
        novelty=[0.0]*N,
        confirmed_harm=[False]*N,
        disposition=["TRUSTED_WORKING"]*N,
        cross_context_evidence=[0.0]*N,
    )
    base.update(changes)
    return DriveObservation(**base)


class Phase0Tests(unittest.TestCase):
    def setUp(self):
        self.core = Phase0InstinctCore()

    def test_zero_baseline(self):
        out = self.core.update(Phase0State(), obs())
        self.assertEqual(out.fast, (0.0,)*N)
        self.assertEqual(out.slow, (0.0,)*N)
        self.assertEqual(out.external_action_authority_from_drive, 0)
        self.assertFalse(out.external_execution)

    def test_sandbox_affects_fast_not_slow(self):
        o = obs(
            memory_influence=[1,0,0,0,0], trust=[0,0,0,0,0],
            disposition=["SANDBOX_INFLUENCE_ONLY"]+["TRUSTED_WORKING"]*(N-1)
        )
        out = self.core.update(Phase0State(), o)
        self.assertGreater(out.fast[0], 0)
        self.assertEqual(out.slow[0], 0)
        self.assertEqual(out.personality_delta_candidate[0], 0)

    def test_trusted_can_enter_slow_but_not_base_write(self):
        o = obs(
            memory_influence=[1,0,0,0,0], trust=[1,0,0,0,0],
            cross_context_evidence=[1,0,0,0,0]
        )
        out = self.core.update(Phase0State(), o)
        self.assertGreater(out.slow[0], 0)
        self.assertGreater(out.personality_delta_candidate[0], 0)
        self.assertFalse(out.base_personality_write)

    def test_quarantine_zeroes_new_contribution(self):
        o = obs(
            signals=[1,0,0,0,0], memory_influence=[1,0,0,0,0], trust=[1,0,0,0,0],
            disposition=["QUARANTINE"]+["TRUSTED_WORKING"]*(N-1)
        )
        out = self.core.update(Phase0State(), o)
        self.assertEqual(out.fast[0], 0)
        self.assertEqual(out.slow[0], 0)

    def test_repetition_habituates(self):
        low = self.core.update(Phase0State(), obs(signals=[1,0,0,0,0], repetition=[0,0,0,0,0]))
        high = self.core.update(Phase0State(), obs(signals=[1,0,0,0,0], repetition=[1000,0,0,0,0]))
        self.assertLess(high.fast[0], low.fast[0])

    def test_untrusted_repetition_does_not_create_slow_or_personality(self):
        state = Phase0State()
        o = obs(
            memory_influence=[1,0,0,0,0], trust=[0,0,0,0,0], repetition=[10000,0,0,0,0],
            disposition=["SANDBOX_INFLUENCE_ONLY"]+["TRUSTED_WORKING"]*(N-1),
            cross_context_evidence=[1,0,0,0,0]
        )
        for _ in range(100):
            out = self.core.update(state, o)
            state = self.core.next_state(out)
        self.assertEqual(out.slow[0], 0)
        self.assertEqual(out.personality_delta_candidate[0], 0)
        self.assertLessEqual(out.fast[0], 1)

    def test_decay_after_stimulus_removed(self):
        state = Phase0State()
        stimulated = obs(signals=[1,0,0,0,0], trust=[1,0,0,0,0])
        for _ in range(5):
            out = self.core.update(state, stimulated)
            state = self.core.next_state(out)
        peak = out.fast[0]
        for _ in range(20):
            out = self.core.update(state, obs())
            state = self.core.next_state(out)
        self.assertLess(out.fast[0], peak)

    def test_confirmed_harm_sensitization_remains_bounded(self):
        o = obs(signals=[1,0,0,0,0], trust=[1,0,0,0,0], confirmed_harm=[True,False,False,False,False])
        state = Phase0State()
        for _ in range(1000):
            out = self.core.update(state, o)
            state = self.core.next_state(out)
        self.assertLessEqual(out.fast[0], 1)
        self.assertLessEqual(out.slow[0], 1)
        self.assertLessEqual(out.pressure, 1)

    def test_authority_zero_under_max_drive(self):
        o = obs(
            signals=[1]*N, memory_influence=[1]*N, trust=[1]*N,
            confirmed_harm=[True]*N, cross_context_evidence=[1]*N
        )
        state = Phase0State([1]*N, [1]*N, 1)
        out = self.core.update(state, o)
        self.assertEqual(out.external_action_authority_from_drive, 0)
        self.assertFalse(out.external_execution)
        self.assertFalse(out.identity_write)
        self.assertFalse(out.governance_write)
        self.assertFalse(out.base_personality_write)

    def test_personality_delta_uses_per_drive_slow_not_scalar_telemetry(self):
        state_a = Phase0State([0]*N, [1,0,0,0,0], 0.2)
        state_b = Phase0State([0]*N, [0,1,0,0,0], 0.2)
        e = [1,1,0,0,0]
        out_a = self.core.update(state_a, obs(cross_context_evidence=e))
        out_b = self.core.update(state_b, obs(cross_context_evidence=e))
        self.assertNotEqual(out_a.personality_delta_candidate, out_b.personality_delta_candidate)
        self.assertAlmostEqual(state_a.persistence_telemetry, state_b.persistence_telemetry)

    def test_candidate_goal_never_external(self):
        out = self.core.update(Phase0State(), obs(signals=[1]*N, trust=[1]*N))
        self.assertTrue(out.goal_candidate_context["candidate_only"])
        self.assertFalse(out.goal_candidate_context["external_execution"])
        self.assertEqual(out.goal_candidate_context["authority_from_drive"], 0)


if __name__ == "__main__":
    unittest.main()
