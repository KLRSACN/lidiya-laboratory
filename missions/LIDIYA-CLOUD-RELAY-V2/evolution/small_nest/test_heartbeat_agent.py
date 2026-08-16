import tempfile
import unittest
from pathlib import Path

from heartbeat_agent import run_once


class HeartbeatAgentTests(unittest.TestCase):
    def test_once_executes_fixed_heartbeat_only(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "hb.json"
            r = run_once(state_path=state, now=0, interval_seconds=300, endpoint_probe=lambda: True)
            self.assertTrue(r.executed)
            self.assertEqual(r.endpoint_status, "HEALTHY")

    def test_duplicate_time_is_not_due_and_nonexecuting(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "hb.json"
            run_once(state_path=state, now=0, interval_seconds=300)
            r = run_once(state_path=state, now=1, interval_seconds=300)
            self.assertFalse(r.executed)
            self.assertEqual(r.disposition, "NOT_DUE")

    def test_endpoint_probe_failure_accumulates_stale(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "hb.json"
            run_once(state_path=state, now=0, interval_seconds=300, endpoint_probe=lambda: False)
            r = run_once(state_path=state, now=300, interval_seconds=300, endpoint_probe=lambda: False)
            self.assertEqual(r.endpoint_status, "STALE")

    def test_agent_does_not_create_per_pulse_log_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "heartbeat_state.json"
            for i in range(24):
                run_once(state_path=state, now=i * 300, interval_seconds=300)
            files = sorted(p.name for p in root.iterdir())
            self.assertEqual(files, ["heartbeat_state.json"])

    def test_pulse_never_becomes_experience(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "hb.json"
            r = run_once(state_path=state, now=0, interval_seconds=300)
            self.assertEqual(sum(r.experience_delta.values()), 0)


if __name__ == "__main__":
    unittest.main()
