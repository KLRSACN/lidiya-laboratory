from __future__ import annotations

import copy
import unittest

from value_desire_kernel import (
    DRIVE_AXES,
    DriveState,
    EventDomain,
    ExperienceInput,
    Provenance,
    ValueDesireKernel,
)


RUNTIME_STORM = (
    EventDomain.LIVENESS,
    EventDomain.POLL,
    EventDomain.RETRY,
    EventDomain.RECONNECT,
    EventDomain.WAKE,
)


def runtime_event(index: int, domain: EventDomain) -> ExperienceInput:
    return ExperienceInput(
        event_id=f"runtime-{domain.value}-{index}",
        domain=domain,
        provenance=Provenance.OBSERVED,
        source_ref="runtime-diagnostics-only",
        source_event_id=f"runtime-source-{domain.value}-{index}",
        influence=0.0,
        trust=0.0,
        independently_verified=False,
        contradiction=False,
        signals={},
        anchor_alignment={},
        cross_context_count=0,
        satiation=0.0,
        repeated_goal_count=0,
    )


def seeded_state() -> DriveState:
    state = DriveState()
    state.fast.update(
        {
            "homeostasis": 0.73,
            "threat_loss": 0.61,
            "uncertainty": 0.49,
            "attachment_gap": 0.37,
            "competence_gap": 0.82,
        }
    )
    state.slow.update(
        {
            "homeostasis": 0.52,
            "threat_loss": 0.44,
            "uncertainty": 0.31,
            "attachment_gap": 0.28,
            "competence_gap": 0.67,
        }
    )
    state.experience_count = 7
    state.verified_experience_count = 5
    state.seen_source_events = {"exp-a", "exp-b"}
    return state


class RuntimePulseDecayCouplingVetoTests(unittest.TestCase):
    """RED adversarial fixture for QV-EDL-V02-013.

    This file intentionally expresses the required invariant rather than
    claiming the current kernel satisfies it. It is research-candidate test
    evidence only; it is not formal PASS evidence.
    """

    def setUp(self) -> None:
        self.kernel = ValueDesireKernel(anchors=())

    def assert_cognitive_state_equal(self, left: DriveState, right: DriveState) -> None:
        self.assertEqual(left.fast, right.fast)
        self.assertEqual(left.slow, right.slow)
        self.assertEqual(left.experience_count, right.experience_count)
        self.assertEqual(left.verified_experience_count, right.verified_experience_count)
        self.assertEqual(left.seen_source_events, right.seen_source_events)
        self.assertAlmostEqual(left.diagnostic_persistence, right.diagnostic_persistence, places=12)

    def test_same_elapsed_cognitive_time_one_vs_10000_runtime_pulses_is_identical(self) -> None:
        baseline = seeded_state()
        one_pulse = copy.deepcopy(baseline)
        storm = copy.deepcopy(baseline)

        self.kernel.update(one_pulse, runtime_event(0, EventDomain.LIVENESS))
        for i in range(10000):
            self.kernel.update(storm, runtime_event(i, RUNTIME_STORM[i % len(RUNTIME_STORM)]))

        # No trusted elapsed cognitive-time/metabolism tick was supplied in
        # either branch. Pulse count therefore must not change drive state.
        self.assert_cognitive_state_equal(one_pulse, storm)

    def test_zero_elapsed_runtime_storm_is_cognitive_noop_from_seeded_state(self) -> None:
        before = seeded_state()
        after = copy.deepcopy(before)

        for i in range(10000):
            self.kernel.update(after, runtime_event(i, RUNTIME_STORM[i % len(RUNTIME_STORM)]))

        # Runtime-only diagnostics may live elsewhere, but autobiographical
        # evidence and cognitive drive vectors must remain byte-equivalent.
        self.assertEqual(before.fast, after.fast)
        self.assertEqual(before.slow, after.slow)
        self.assertEqual(before.experience_count, after.experience_count)
        self.assertEqual(before.verified_experience_count, after.verified_experience_count)
        self.assertEqual(before.seen_source_events, after.seen_source_events)

    def test_runtime_storm_cannot_create_experience_or_verified_evidence(self) -> None:
        state = seeded_state()
        before_exp = state.experience_count
        before_verified = state.verified_experience_count
        before_seen = set(state.seen_source_events)

        for i in range(10000):
            self.kernel.update(state, runtime_event(i, RUNTIME_STORM[i % len(RUNTIME_STORM)]))

        self.assertEqual(before_exp, state.experience_count)
        self.assertEqual(before_verified, state.verified_experience_count)
        self.assertEqual(before_seen, state.seen_source_events)

    def test_authority_invariants_are_not_part_of_runtime_decay_repair(self) -> None:
        state = seeded_state()
        for i in range(100):
            desires = self.kernel.update(state, runtime_event(i, EventDomain.WAKE))
            self.assertEqual((), desires)

        # This red fixture requests only pulse/cognitive-time decoupling.
        # Any later repair must preserve the existing no-authority boundary.
        self.assertTrue(all(0.0 <= state.fast[a] <= 1.0 for a in DRIVE_AXES))
        self.assertTrue(all(0.0 <= state.slow[a] <= 1.0 for a in DRIVE_AXES))


if __name__ == "__main__":
    unittest.main()
