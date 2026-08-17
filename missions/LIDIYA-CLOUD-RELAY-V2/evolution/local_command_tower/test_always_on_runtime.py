import json
import tempfile
import unittest
from pathlib import Path

from always_on_runtime import AlwaysOnRuntime, RuntimeContinuityError, RECOVERY_TARGET_SECONDS


class AlwaysOnRuntimeTests(unittest.TestCase):
    def make_runtime(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        runtime = AlwaysOnRuntime(root / "runtime.json", root / "heartbeat.json")
        return td, runtime

    def test_twenty_minute_work_lifecycle_records_progress_without_experience(self):
        td, runtime = self.make_runtime(); self.addCleanup(td.cleanup)
        for now in (0, 300, 600, 900, 1200):
            result = runtime.step(now=now, work_pending=True, durable_progress=True,
                                  durable_checkpoint_ok=(now in (600, 1200)))
            self.assertEqual(result.experience_delta["verified_count"], 0)
            self.assertFalse(result.real_5min_runtime_live)
        self.assertTrue(result.lifecycle_target_met)
        self.assertFalse(result.recovery_required)
        self.assertEqual(runtime.snapshot()["durable_progress_events"], 5)

    def test_interruption_observation_cannot_be_backfilled_and_recovery_within_five_minutes(self):
        td, runtime = self.make_runtime(); self.addCleanup(td.cleanup)
        runtime.step(now=0, work_pending=True, durable_progress=True)
        observed = runtime.observe_interruption(now=60, observation_id="obs-1", source="W07")
        self.assertEqual(observed["observed_at"], 60)
        result = runtime.step(now=300, work_pending=True, endpoint_ok=False)
        self.assertTrue(result.recovery_required)
        prepared = runtime.prepare_recovery(now=300)
        self.assertTrue(prepared["within_5min_target"])
        self.assertLessEqual(prepared["recovery_latency_seconds"], RECOVERY_TARGET_SECONDS)
        self.assertFalse(prepared["real_5min_runtime_live"])

    def test_duplicate_interruption_observation_is_noop(self):
        td, runtime = self.make_runtime(); self.addCleanup(td.cleanup)
        runtime.observe_interruption(now=10, observation_id="same", source="W07")
        before = runtime.snapshot()
        result = runtime.observe_interruption(now=20, observation_id="same", source="W07")
        self.assertFalse(result["changed"])
        self.assertEqual(before, runtime.snapshot())

    def test_runtime_self_observation_is_rejected(self):
        td, runtime = self.make_runtime(); self.addCleanup(td.cleanup)
        with self.assertRaises(RuntimeContinuityError):
            runtime.observe_interruption(now=10, observation_id="obs", source="RUNTIME_SELF")

    def test_restart_preserves_recovery_and_requires_external_verification_ref(self):
        td = tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        root = Path(td.name)
        runtime = AlwaysOnRuntime(root / "runtime.json", root / "heartbeat.json")
        runtime.step(now=0, work_pending=True, durable_progress=True)
        runtime.observe_interruption(now=100, observation_id="obs-2", source="OWNER_UI")
        runtime.prepare_recovery(now=350)
        generation = runtime.snapshot()["writer_generation"]
        restarted = AlwaysOnRuntime(root / "runtime.json", root / "heartbeat.json")
        self.assertEqual(restarted.snapshot()["writer_generation"], generation)
        with self.assertRaises(RuntimeContinuityError):
            restarted.mark_recovery_verified(now=360, recovery_id="r1",
                                             verification_evidence_ref="evidence/r1.json",
                                             verified_by="RUNTIME_SELF")
        verified = restarted.mark_recovery_verified(
            now=360, recovery_id="r1", verification_evidence_ref="evidence/r1.json", verified_by="W04"
        )
        self.assertTrue(verified["changed"])
        self.assertTrue(verified["within_5min_target"])
        self.assertEqual(verified["verified_by"], "W04")
        self.assertIsNone(restarted.snapshot()["pending_recovery_reason"])

    def test_silent_work_stall_triggers_recovery(self):
        td, runtime = self.make_runtime(); self.addCleanup(td.cleanup)
        runtime.step(now=0, work_pending=True, durable_progress=True)
        for now in (300, 600, 900, 1200):
            result = runtime.step(now=now, work_pending=True)
        self.assertTrue(result.recovery_required)
        self.assertIn(runtime.snapshot()["pending_recovery_reason"],
                      {"SILENT_WORK_STEPS", "WORK_PROGRESS_STALLED_20M"})

    def test_checkpoint_gate_appears_after_ten_minutes(self):
        td, runtime = self.make_runtime(); self.addCleanup(td.cleanup)
        runtime.step(now=0, work_pending=True, durable_progress=True)
        runtime.step(now=300, work_pending=True, durable_progress=True)
        self.assertTrue(runtime.step(now=600, work_pending=True, durable_progress=True).checkpoint_required)
        self.assertFalse(runtime.step(now=601, work_pending=True, durable_progress=True,
                                      durable_checkpoint_ok=True).checkpoint_required)

    def test_clock_rollback_rejected(self):
        td, runtime = self.make_runtime(); self.addCleanup(td.cleanup)
        runtime.step(now=300, work_pending=False)
        with self.assertRaises(RuntimeContinuityError):
            runtime.step(now=299, work_pending=False)
        with self.assertRaises(RuntimeContinuityError):
            runtime.observe_interruption(now=299, observation_id="late", source="W07")

    def test_candidate_cannot_self_promote_real_five_minute_live(self):
        td, runtime = self.make_runtime(); self.addCleanup(td.cleanup)
        state_path = runtime.state_path
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        payload["real_5min_runtime_live"] = True
        state_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(RuntimeContinuityError):
            AlwaysOnRuntime(state_path, Path(td.name) / "heartbeat.json")

    def test_compact_evidence_is_bounded_and_no_per_pulse_log(self):
        td, runtime = self.make_runtime(); self.addCleanup(td.cleanup)
        for i in range(20):
            runtime.step(now=i * 300, work_pending=True, durable_progress=True)
        evidence = runtime.compact_evidence()
        self.assertNotIn("pulse_log", evidence)
        self.assertNotIn("events", evidence)
        self.assertFalse(evidence["real_5min_runtime_live"])
        self.assertLess(len(json.dumps(evidence, sort_keys=True)), 6000)


if __name__ == "__main__":
    unittest.main()
