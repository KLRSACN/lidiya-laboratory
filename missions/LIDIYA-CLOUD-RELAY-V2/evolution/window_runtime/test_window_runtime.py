import unittest

from window_runtime import RuntimeRejected, WindowRuntime


class WindowRuntimeTests(unittest.TestCase):
    def make(self, **kw):
        return WindowRuntime(
            role="LIDIYA-INNER-CORE-ARCHITECT",
            authority_fingerprint="AUTH-123",
            home_revision="HOME-REV-51",
            **kw,
        )

    def test_bootstrap_loads_required_modules(self):
        rt=self.make()
        out=rt.bootstrap()
        self.assertEqual(out["status"],"BOOTSTRAPPED_CANDIDATE")
        self.assertIn("NAVIGATION_SENTINEL",out["modules"])
        self.assertIn("MIRROR_REFLECTOR_FINAL_PULSE",out["modules"])
        self.assertTrue(out["baseline_metabolic_check"])
        self.assertTrue(out["p_base_read_only"])

    def test_one_minute_liveness_canary_allowed_but_not_subminute(self):
        self.make(liveness_interval_seconds=60)
        with self.assertRaises(RuntimeRejected): self.make(liveness_interval_seconds=59)

    def test_model_wake_floor_is_five_minutes(self):
        with self.assertRaises(RuntimeRejected): self.make(wake_escalation_floor_seconds=299)

    def test_active_endpoint_heartbeat_does_not_rewake_model(self):
        rt=self.make(liveness_interval_seconds=60)
        wakes=0
        for i in range(1,31):
            out=rt.pulse(i*60,pulse_id=f"p{i}",endpoint_alive=True,pending_work=True)
            wakes+=int(out["wake_requested"])
        self.assertEqual(wakes,0)

    def test_stale_endpoint_wakes_only_after_floor(self):
        rt=self.make(liveness_interval_seconds=60,wake_escalation_floor_seconds=300)
        for i in range(1,5):
            out=rt.pulse(i*60,pulse_id=f"p{i}",endpoint_alive=False,pending_work=True)
            self.assertFalse(out["wake_requested"])
        out=rt.pulse(300,pulse_id="p5",endpoint_alive=False,pending_work=True)
        self.assertTrue(out["wake_requested"])
        self.assertEqual(out["wake_reason"],"STALE_ENDPOINT_PENDING_WORK")

    def test_rate_limit_defers_wake_without_reset(self):
        rt=self.make(liveness_interval_seconds=60)
        for i in range(1,5):
            rt.pulse(i*60,pulse_id=f"p{i}",endpoint_alive=False,pending_work=True,rate_limited=True)
        out=rt.pulse(300,pulse_id="p5",endpoint_alive=False,pending_work=True,rate_limited=True)
        self.assertFalse(out["wake_requested"])
        self.assertEqual(out["wake_reason"],"DEFER_RATE_LIMIT")
        self.assertEqual(rt.state.authority_fingerprint,"AUTH-123")

    def test_duplicate_pulse_exactly_once(self):
        rt=self.make()
        first=rt.pulse(300,pulse_id="same",endpoint_alive=True,pending_work=False)
        second=rt.pulse(300,pulse_id="same",endpoint_alive=True,pending_work=False)
        self.assertEqual(first["pulse_sequence"],1)
        self.assertEqual(second["status"],"DUPLICATE_PULSE_NO_OP")
        self.assertEqual(rt.state.pulse_sequence,1)

    def test_stale_writer_rejected(self):
        rt=self.make(writer_generation=3)
        out=rt.pulse(300,pulse_id="p1",endpoint_alive=True,pending_work=True,writer_generation=2)
        self.assertEqual(out["status"],"STALE_WRITER_REJECTED")
        self.assertEqual(rt.state.pulse_sequence,0)

    def test_ten_minute_check_and_thirty_minute_compaction(self):
        rt=self.make(liveness_interval_seconds=60)
        first=rt.pulse(60,pulse_id="p1",endpoint_alive=True,pending_work=True)
        self.assertFalse(first["metabolic_check"])
        self.assertFalse(first["micro_compaction_due"])
        for i in range(2,10):
            out=rt.pulse(i*60,pulse_id=f"p{i}",endpoint_alive=True,pending_work=True)
            self.assertFalse(out["metabolic_check"])
            self.assertFalse(out["micro_compaction_due"])
        out=rt.pulse(600,pulse_id="p10",endpoint_alive=True,pending_work=True)
        self.assertTrue(out["metabolic_check"])
        self.assertFalse(out["micro_compaction_due"])
        out=rt.pulse(1800,pulse_id="p30",endpoint_alive=True,pending_work=True)
        self.assertTrue(out["micro_compaction_due"])

    def test_pressure_can_trigger_early_compaction(self):
        rt=self.make()
        out=rt.pulse(300,pulse_id="p1",endpoint_alive=True,pending_work=True,metabolism_pressure=0.8)
        self.assertTrue(out["micro_compaction_due"])

    def test_backlog_can_trigger_early_compaction(self):
        rt=self.make()
        out=rt.pulse(300,pulse_id="p1",endpoint_alive=True,pending_work=True,backlog=20)
        self.assertTrue(out["micro_compaction_due"])

    def test_1440_one_minute_pulses_do_not_inflate_memory_or_personality(self):
        rt=self.make(liveness_interval_seconds=60)
        rt.record_experience("event-1","prov-1")
        before=rt.memory_guard_snapshot()
        for i in range(1,1441):
            rt.pulse(i*60,pulse_id=f"p{i}",endpoint_alive=True,pending_work=True)
        after=rt.memory_guard_snapshot()
        self.assertEqual(before,after)
        self.assertEqual(after["recurrence"],1)
        self.assertEqual(after["verified_count"],1)

    def test_distinct_experience_not_heartbeat_changes_recurrence(self):
        rt=self.make(liveness_interval_seconds=60)
        for i in range(1,61): rt.pulse(i*60,pulse_id=f"p{i}",endpoint_alive=True,pending_work=True)
        self.assertEqual(rt.memory_guard_snapshot()["recurrence"],0)
        rt.record_experience("event-real","prov-real")
        self.assertEqual(rt.memory_guard_snapshot()["recurrence"],1)

    def test_duplicate_experience_no_op(self):
        rt=self.make()
        rt.record_experience("e","p")
        out=rt.record_experience("e","p")
        self.assertEqual(out["status"],"DUPLICATE_EXPERIENCE_NO_OP")
        self.assertEqual(rt.memory_guard_snapshot()["recurrence"],1)

    def test_continuation_overlap_extends_active_work_without_new_window(self):
        rt=self.make()
        out=rt.continuation_decision(current_work_complete=True,next_authorized_action="NEXT_SAFE_STEP")
        self.assertEqual(out["decision"],"KEEP_ACTIVE_OVERLAP")
        self.assertTrue(out["emit_final_reflection"])
        self.assertFalse(out["create_new_window"])

    def test_rate_limited_continuation_checkpoints_instead_of_spawning(self):
        rt=self.make()
        out=rt.continuation_decision(current_work_complete=True,next_authorized_action="NEXT_SAFE_STEP",rate_limited=True)
        self.assertEqual(out["decision"],"CHECKPOINT_REFLECT_DEFER")
        self.assertFalse(out["create_new_window"])

    def test_final_reflection_emits_continue_before_release(self):
        rt=self.make()
        out=rt.final_reflection(1000,reflection_id="r1",what_completed="part A",what_remains="part B",next_authorized_action="CONTINUE_B",mission_pointer="M/8",pending_packet="p.json",pending_sha256="abc",latest_evidence_ref="e.json",return_condition="finish B",continue_requested=True)
        self.assertEqual(out["status"],"REFLECT_CONTINUE_EMITTED")
        self.assertTrue(out["wake_candidate"])
        self.assertEqual(out["reflection"]["next_authorized_action"],"CONTINUE_B")

    def test_duplicate_final_reflection_is_no_op(self):
        rt=self.make()
        kwargs=dict(reflection_id="r1",what_completed="a",what_remains="b",next_authorized_action="c",mission_pointer="m",pending_packet=None,pending_sha256=None,latest_evidence_ref=None,return_condition="x",continue_requested=True)
        rt.final_reflection(1000,**kwargs)
        out=rt.final_reflection(1001,**kwargs)
        self.assertEqual(out["status"],"DUPLICATE_REFLECTION_NO_OP")

    def test_monotonic_rollback_rejected(self):
        rt=self.make()
        rt.pulse(300,pulse_id="p1",endpoint_alive=True,pending_work=False)
        with self.assertRaises(RuntimeRejected): rt.pulse(299,pulse_id="p2",endpoint_alive=True,pending_work=False)

    def test_material_event_can_escalate_immediately(self):
        rt=self.make(liveness_interval_seconds=60)
        out=rt.pulse(60,pulse_id="p1",endpoint_alive=True,pending_work=True,material_event=True)
        self.assertTrue(out["wake_requested"])
        self.assertEqual(out["wake_reason"],"MATERIAL_EVENT")

    def test_routine_pulse_never_requests_per_pulse_durable_log(self):
        rt=self.make(liveness_interval_seconds=60)
        for i in range(1,20):
            out=rt.pulse(i*60,pulse_id=f"p{i}",endpoint_alive=True,pending_work=True)
            self.assertFalse(out["durable_per_pulse_log"])


if __name__ == "__main__":
    unittest.main()
