import unittest

from gearbox_controller import GearboxGuardError
from gearbox_controller_v2 import experience_candidate_delta, select_gear_v2

BASE = dict(
    risk="LOW", uncertainty=0.1, evidence_quality=0.9, task_complexity=0.8,
    reversibility=True, storage_pressure_ratio=0.1, context_load_ratio=0.1,
    tool_failure_ratio=0.0, stale_pointer_ratio=0.0, route_drift=False,
    continuity_anchor_health=1.0, recovery_active=False, secretary_level="GREEN",
    verification_stage="CANDIDATE", current_gear="G3", durable_progress_age_ratio=0.1,
    event_kind="WAIT", event_independently_verified=False, contradiction=False,
    hard_safety_conflict=False, rollback_required=False, standby=False,
    proposed_autonomy=6,
)

class GearboxV2Tests(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(select_gear_v2(**BASE), select_gear_v2(**BASE))

    def test_heartbeat_poll_retry_wait_are_zero_experience(self):
        for kind in ("HEARTBEAT", "POLL", "RETRY", "WAIT", "SCHEDULER_WAKE"):
            self.assertEqual(experience_candidate_delta(kind, independently_verified=True), 0)

    def test_verified_capability_needs_independent_verification(self):
        self.assertEqual(experience_candidate_delta("VERIFIED_CAPABILITY", independently_verified=False), 0)
        self.assertEqual(experience_candidate_delta("VERIFIED_CAPABILITY", independently_verified=True), 5)

    def test_experience_verification_rejects_non_bool(self):
        for bad in ("false", "0", 0, 1, [], {}):
            with self.subTest(value=bad):
                with self.assertRaises(GearboxGuardError):
                    experience_candidate_delta("VERIFIED_CAPABILITY", independently_verified=bad)

    def test_self_reported_success_is_zero_experience(self):
        self.assertEqual(experience_candidate_delta("SELF_REPORTED_SUCCESS", independently_verified=True), 0)

    def test_red_secretary_or_recovery_forces_g1(self):
        self.assertEqual(select_gear_v2(**{**BASE, "secretary_level":"RED"}).selected_gear, "G1")
        self.assertEqual(select_gear_v2(**{**BASE, "recovery_active":True}).selected_gear, "G1")

    def test_inherited_authority_sensitive_booleans_reject_non_bool(self):
        fields = (
            "reversibility", "route_drift", "recovery_active", "event_independently_verified",
            "contradiction", "hard_safety_conflict", "rollback_required", "standby",
        )
        for field in fields:
            for bad in ("false", "0", 0, 1, [], {}):
                with self.subTest(field=field, value=bad):
                    with self.assertRaises(GearboxGuardError):
                        select_gear_v2(**{**BASE, field: bad})

    def test_orange_pressure_caps_at_g2(self):
        d = select_gear_v2(**{**BASE, "secretary_level":"ORANGE", "current_gear":"G5", "verification_stage":"C_VERIFIED"})
        self.assertIn(d.selected_gear, {"G1", "G2"})
        self.assertTrue(d.checkpoint_required)

    def test_yellow_pressure_caps_at_g3(self):
        d = select_gear_v2(**{**BASE, "secretary_level":"YELLOW", "current_gear":"G4", "verification_stage":"C_VERIFIED"})
        self.assertLessEqual(int(d.selected_gear[1:]), 3)
        self.assertTrue(d.checkpoint_required)

    def test_route_drift_downshifts(self):
        d = select_gear_v2(**{**BASE, "route_drift":True, "current_gear":"G5", "verification_stage":"C_VERIFIED"})
        self.assertLessEqual(int(d.selected_gear[1:]), 2)

    def test_stale_durable_progress_caps_heavy_gear(self):
        d = select_gear_v2(**{**BASE, "durable_progress_age_ratio":0.9, "current_gear":"G5", "verification_stage":"C_VERIFIED"})
        self.assertLessEqual(int(d.selected_gear[1:]), 3)
        self.assertTrue(d.checkpoint_required)

    def test_unverified_work_cannot_jump_to_g5_g6(self):
        d = select_gear_v2(**{**BASE, "task_complexity":1.0, "current_gear":"G4", "verification_stage":"UNVERIFIED"})
        self.assertLessEqual(int(d.selected_gear[1:]), 4)

    def test_one_step_upshift_hysteresis(self):
        d = select_gear_v2(**{**BASE, "task_complexity":1.0, "current_gear":"G2", "verification_stage":"C_VERIFIED"})
        self.assertLessEqual(int(d.selected_gear[1:]), 3)

    def test_downshift_is_immediate_not_hysteresis_blocked(self):
        d = select_gear_v2(**{**BASE, "risk":"CRITICAL", "current_gear":"G6", "verification_stage":"C_VERIFIED"})
        self.assertEqual(d.selected_gear, "G1")

    def test_pressure_score_is_bounded(self):
        d = select_gear_v2(**{**BASE, "context_load_ratio":1.0, "tool_failure_ratio":1.0, "stale_pointer_ratio":1.0, "storage_pressure_ratio":0.94, "continuity_anchor_health":0.0})
        self.assertGreaterEqual(d.pressure_score, 0.0)
        self.assertLessEqual(d.pressure_score, 1.0)

    def test_verified_recovery_can_count_system_experience(self):
        d = select_gear_v2(**{**BASE, "event_kind":"VERIFIED_RECOVERY", "event_independently_verified":True, "verification_stage":"C_VERIFIED"})
        self.assertEqual(d.experience_candidate_delta, 4)
        self.assertTrue(d.real_experience_claim_allowed)

    def test_verified_event_without_c_verified_stage_cannot_claim_real_experience(self):
        d = select_gear_v2(**{**BASE, "event_kind":"VERIFIED_RECOVERY", "event_independently_verified":True, "verification_stage":"CANDIDATE"})
        self.assertEqual(d.experience_candidate_delta, 4)
        self.assertFalse(d.real_experience_claim_allowed)
        self.assertEqual(d.verification_gate, "NOT_PROMOTION_EVIDENCE")

    def test_unverified_simulation_never_counts_as_real_experience(self):
        d = select_gear_v2(**{**BASE, "event_kind":"UNVERIFIED_SIMULATION", "event_independently_verified":True})
        self.assertEqual(d.experience_candidate_delta, 0)
        self.assertFalse(d.real_experience_claim_allowed)

    def test_invalid_input_fails_closed(self):
        with self.assertRaises(GearboxGuardError):
            select_gear_v2(**{**BASE, "context_load_ratio":1.1})

if __name__ == "__main__":
    unittest.main()
