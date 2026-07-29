from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import service_control


class ServiceControlTests(unittest.TestCase):
    def test_status_stopped_without_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = service_control.status_service(Path(tmp))
            self.assertEqual(result["status"], "STOPPED")
            self.assertIsNone(result["pid"])

    def test_status_reads_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "navigator_state"
            state.mkdir(parents=True)
            (state / "heartbeat.json").write_text(
                json.dumps({"status": "RUNNING", "ticks": 3}),
                encoding="utf-8",
            )
            result = service_control.status_service(root)
            self.assertEqual(result["heartbeat"]["ticks"], 3)

    def test_start_writes_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            process = Mock(pid=4321)
            with patch.object(service_control.subprocess, "Popen", return_value=process):
                with patch.object(service_control, "_is_running", return_value=False):
                    result = service_control.start_service(
                        root,
                        poll_seconds=1.0,
                        python_executable="python-test",
                    )
            self.assertEqual(result["status"], "STARTED")
            self.assertEqual((root / "navigator_state" / "service.pid").read_text(), "4321")

    def test_start_blocks_duplicate_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "navigator_state"
            state.mkdir(parents=True)
            (state / "service.pid").write_text("99", encoding="utf-8")
            with patch.object(service_control, "_is_running", return_value=True):
                with self.assertRaisesRegex(service_control.ServiceControlError, "already running"):
                    service_control.start_service(root)

    def test_stop_removes_stale_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "navigator_state"
            state.mkdir(parents=True)
            pid_path = state / "service.pid"
            pid_path.write_text("77", encoding="utf-8")
            with patch.object(service_control, "_is_running", return_value=False):
                result = service_control.stop_service(root)
            self.assertEqual(result["status"], "STALE_PID_REMOVED")
            self.assertFalse(pid_path.exists())


if __name__ == "__main__":
    unittest.main()
