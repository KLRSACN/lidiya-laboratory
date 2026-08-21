import unittest
from types import SimpleNamespace

from gearbox_pressure_chronicity_neutrality_shadow_v01 import (
    chronicity_boundaries, neutral_runtime_state, neutralize_pressure_shadow,
    observe_authenticated_pressure_shadow,
)


def projection(level, value):
    return SimpleNamespace(secretary_level=level, pressure={
        "context_load_ratio": value,
        "tool_failure_ratio": value / 2,
        "stale_pointer_ratio": value / 3,
        "durable_progress_age_ratio": value,
        "continuity_anchor_health": 1.0 - value / 2,
        "storage_pressure_ratio": value / 4,
    })


class PressureChronicityNeutralityTests(unittest.TestCase):
    def test_signed_pressure_chronicity_neutrality_10000_ab(self):
        a = neutral_runtime_state()
        a = observe_authenticated_pressure_shadow(a, projection("GREEN", 0.0))
        a = neutralize_pressure_shadow(a)

        b = neutral_runtime_state()
        for i in range(10000):
            level = "YELLOW" if i % 2 == 0 else "ORANGE"
            b = observe_authenticated_pressure_shadow(b, projection(level, 0.8))
        b = observe_authenticated_pressure_shadow(b, projection("GREEN", 0.0))
        b = neutralize_pressure_shadow(b)

        self.assertEqual(a.secretary_level, b.secretary_level)
        self.assertEqual(a.pressure, b.pressure)
        self.assertEqual(a.operational_observation_count, b.operational_observation_count)
        self.assertEqual(a.cognitive.bytes_projection(), b.cognitive.bytes_projection())

    def test_pressure_is_ephemeral_but_current_projection_is_visible(self):
        s = observe_authenticated_pressure_shadow(neutral_runtime_state(), projection("ORANGE", 0.8))
        self.assertEqual("ORANGE", s.secretary_level)
        self.assertEqual(1, s.operational_observation_count)
        self.assertEqual((), s.cognitive.accepted_experience_ids)
        n = neutralize_pressure_shadow(s)
        self.assertEqual(0, n.operational_observation_count)
        self.assertEqual("GREEN", n.secretary_level)

    def test_boundary_has_zero_learning_and_formal_effect(self):
        b = chronicity_boundaries()
        self.assertFalse(b["pressure_history_persisted"])
        self.assertFalse(b["operational_counter_survives_neutralization"])
        for key in ("experience_delta", "appraisal_delta", "drive_delta", "exploration_delta", "preference_delta", "personality_delta", "trauma_or_relief_delta"):
            self.assertEqual(0, b[key])
        self.assertFalse(b["p_base_mutation"])
        self.assertFalse(b["formal_mutation_allowed"])


if __name__ == "__main__": unittest.main()
