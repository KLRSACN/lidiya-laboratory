import unittest

from gearbox_controller_v2_1 import aggregate_experience_events, select_gear_v2_1

BASE = dict(
    risk="LOW", uncertainty=0.1, evidence_quality=0.9, task_complexity=0.8,
    reversibility=True, storage_pressure_ratio=0.1, context_load_ratio=0.1,
    tool_failure_ratio=0.0, stale_pointer_ratio=0.0, route_drift=False,
    continuity_anchor_health=1.0, recovery_active=False, secretary_level="GREEN",
    verification_stage="C_VERIFIED", current_gear="G3", durable_progress_age_ratio=0.1,
    event_kind="WAIT", event_independently_verified=False, contradiction=False,
    hard_safety_conflict=False, rollback_required=False, standby=False,
    proposed_autonomy=6,
)


class GearboxV21Tests(unittest.TestCase):
    def test_stale_red_secretary_is_ignored(self):
        d = select_gear_v2_1(**{**BASE, "secretary_level":"RED"}, secretary_signal_fresh=False)
        self.assertTrue(d.stale_secretary_ignored)
        self.assertNotEqual(d.selected_gear, "G1")

    def test_fresh_red_secretary_can_brake(self):
        d = select_gear_v2_1(**{**BASE, "secretary_level":"RED"}, secretary_signal_fresh=True)
        self.assertTrue(d.secretary_signal_used)
        self.assertEqual(d.selected_gear, "G1")

    def test_authority_conflict_disables_secretary_signal(self):
        d = select_gear_v2_1(**{**BASE, "secretary_level":"ORANGE"}, secretary_signal_fresh=True, authority_conflict=True)
        self.assertTrue(d.stale_secretary_ignored)
        self.assertFalse(d.secretary_signal_used)

    def test_high_shift_rate_suppresses_nonessential_upshift(self):
        d = select_gear_v2_1(**BASE, secretary_signal_fresh=True, recent_shift_rate_ratio=0.8)
        self.assertLessEqual(int(d.selected_gear[1:]), int(BASE["current_gear"][1:]))
        self.assertTrue(d.thrash_guard_applied)

    def test_safety_downshift_not_blocked_by_thrash_guard(self):
        d = select_gear_v2_1(**{**BASE, "risk":"CRITICAL", "current_gear":"G6"}, secretary_signal_fresh=True, recent_shift_rate_ratio=1.0)
        self.assertEqual(d.selected_gear, "G1")

    def test_heartbeat_does_not_create_verified_experience(self):
        d = select_gear_v2_1(**{**BASE, "event_kind":"HEARTBEAT", "event_independently_verified":True}, secretary_signal_fresh=True)
        self.assertEqual(d.verified_experience_delta, 0)
        self.assertEqual(d.operational_progress_delta, 0)

    def test_verified_recovery_creates_verified_experience_candidate(self):
        d = select_gear_v2_1(**{**BASE, "event_kind":"VERIFIED_RECOVERY", "event_independently_verified":True}, secretary_signal_fresh=True)
        self.assertEqual(d.verified_experience_delta, 4)
        self.assertEqual(d.operational_progress_delta, 0)

    def test_durable_progress_is_operational_not_verified_experience(self):
        d = select_gear_v2_1(**{**BASE, "event_kind":"DURABLE_PROGRESS"}, secretary_signal_fresh=True)
        self.assertEqual(d.verified_experience_delta, 0)
        self.assertEqual(d.operational_progress_delta, 1)

    def test_duplicate_events_do_not_inflate_ledger(self):
        events = [
            {"event_id":"e1","event_kind":"VERIFIED_RECOVERY","independently_verified":True},
            {"event_id":"e1","event_kind":"VERIFIED_RECOVERY","independently_verified":True},
        ]
        r = aggregate_experience_events(events)
        self.assertEqual(r.verified_experience, 4)
        self.assertEqual(r.duplicate_events, 1)

    def test_unverified_verified_kind_gets_zero(self):
        r = aggregate_experience_events([
            {"event_id":"e1","event_kind":"VERIFIED_CAPABILITY","independently_verified":False}
        ])
        self.assertEqual(r.verified_experience, 0)

    def test_missing_event_id_is_ignored(self):
        r = aggregate_experience_events([
            {"event_kind":"VERIFIED_CAPABILITY","independently_verified":True}
        ])
        self.assertEqual(r.ignored_events, 1)
        self.assertEqual(r.verified_experience, 0)

    def test_overlay_has_no_formal_mutation_authority(self):
        d = select_gear_v2_1(**BASE, secretary_signal_fresh=True)
        self.assertFalse(d.formal_mutation_allowed)


if __name__ == "__main__":
    unittest.main()
