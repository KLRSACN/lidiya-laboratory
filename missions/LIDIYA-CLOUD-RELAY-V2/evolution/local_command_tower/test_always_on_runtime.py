import json
import tempfile
import unittest
from pathlib import Path

from always_on_runtime import (
    AlwaysOnRuntime,
    RuntimeContinuityError,
    RECOVERY_TARGET_SECONDS,
)


class AlwaysOnRuntimeTests(unittest.TestCase):
    def make_runtime(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        runtime = AlwaysOnRuntime(root / "runtime.json", root / "heartbeat.json")
        return td, runtime

    def test_twenty_minute_work_lifecycle_records_progress_without_experience(self):
        td, runtime = self.make_runtime()
        self.addCleanup(td.cleanup)
        for now in (0, 300, 600, 900, 1200):
            result = runtime.step(
                now=now,
                work_pending=True,
                durable_progress=True,
                durable_checkpoint_ok=(now in (600, 1200)),
            )
            self.assertEqual(result.experience_delta["verified_count"], 0)
            self.assertFalse(result.real_5min_runtime_live)
        self.assertTrue(result.lifecycle_target_met)
        self.assertFalse(result.recovery_required)
        self.assertEqual(runtime.snapshot()["durable_progress_events"], 5)

    def test_interruption_prepares_recovery_within_five_minutes(self):
        td, runtime = self.make_runtime()
        self.addCleanup(td.cleanup)
        runtime.step(now=0, work_pending=True, durable_progress=True)
        result = runtime.step(
            now=300,
            work_pending=True,
            interruption_observed_at=60,
            endpoint_ok=False,
        )
        self.assertTrue(result.recovery_required)
        prepared = runtime.prepare_recovery(now=300)
        self.assertEqual(prepared["disposition"], "RECOVERY_PREPARED")
        self.assertTrue(prepared["within_5min_target"])
        self.assertLessEqual(prepared["recovery_latency_seconds"], RECOVERY_TARGET_SECONDS)
        self.assertFalse(prepared["real_5min_runtime_live"])

    def test_restart_preserves_recovery_state_and_verified_recovery(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        runtime = AlwaysOnRuntime(root / "runtime.json", root / "heartbeat.json")
        runtime.step(now=0, work_pending=True, durable_progress=True)
        runtime.step(now=300, work_pending=True, endpoint_ok=False, interruption_observed_at=100)
        runtime.prepare_recovery(now=350)
        generation = runtime.snapshot()["writer_generation"]

        restarted = AlwaysOnRuntime(root / "runtime.json", root / "heartbeat.json")
        self.assertEqual(restarted.snapshot()["writer_generation"], generation)
        verified = restarted.mark_recovery_verified(now=360, recovery_id="recovery-1")
        self.assertTrue(verified["changed"])
        self.assertTrue(verified["within_5min_target"])
        self.assertFalse(verified["real_5min_runtime_live"])
        self.assertIsNone(restarted.snapshot()["pending_recovery_reason"])

    def test_silent_work_stall_triggers_recovery(self):
        td, runtime = self.make_runtime()
        self.addCleanup(td.cleanup)
        runtime.step(now=0, work_pending=True, durable_progress=True)
        for now in (300, 600, 900, 1200):
            result = runtime.step(now=now, work_pending=True)
        self.assertTrue(result.recovery_required)
        self.assertIn(runtime.snapshot()["pending_recovery_reason"], {"SILENT_WORK_STEPS", "WORK_PROGRESS_STALLED_20M"})

    def test_checkpoint_gate_appears_after_ten_minutes(self):
        td, runtime = self.make_runtime()
        self.addCleanup(td.cleanup)
        runtime.step(now=0, work_pending=True, durable_progress=True)
        runtime.step(now=300, work_pending=True, durable_progress=True)
        result = runtime.step(now=600, work_pending=True, durable_progress=True)
        self.assertTrue(result.checkpoint_required)
        result = runtime.step(now=601, work_pending=True, durable_progress=True, durable_checkpoint_ok=True)
        self.assertFalse(result.checkpoint_required)

    def test_clock_rollback_rejected(self):
        td, runtime = self.make_runtime()
        self.addCleanup(td.cleanup)
        runtime.step(now=300, work_pending=False)
        with self.assertRaises(RuntimeContinuityError):
            runtime.step(now=299, work_pending=False)

    def test_candidate_cannot_self_promote_real_five_minute_live(self):
        td, runtime = self.make_runtime()
        self.addCleanup(td.cleanup)
        state_path = runtime.state_path
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        payload["real_5min_runtime_live"] = True
        state_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(RuntimeContinuityError):
            AlwaysOnRuntime(state_path, Path(td.name) / "heartbeat.json")

    def test_compact_evidence_is_bounded_and_no_per_pulse_log(self):
        td, runtime = self.make_runtime()
        self.addCleanup(td.cleanup)
        for i in range(20):
            runtime.step(now=i * 300, work_pending=True, durable_progress=True)
        evidence = runtime.compact_evidence()
        self.assertNotIn("pulse_log", evidence)
        self.assertNotIn("events", evidence)
        self.assertFalse(evidence["real_5min_runtime_live"])
        self.assertLess(len(json.dumps(evidence, sort_keys=True)), 5000)


if __name__ == "__main__":
    unittest.main()
