from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from navigator_loop import NavigatorResult
from service_runner import NavigatorServiceRunner, ServiceRunnerError


class _SequenceLoop:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def tick(self):
        if self.index >= len(self.values):
            return None
        value = self.values[self.index]
        self.index += 1
        if isinstance(value, Exception):
            raise value
        return value


class NavigatorServiceRunnerTests(unittest.TestCase):
    def test_processes_results_and_writes_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            loop = _SequenceLoop([
                NavigatorResult("task-1", "SUCCESS", {"verified": True}),
                None,
            ])
            sleeps = []
            runner = NavigatorServiceRunner(
                loop=loop,
                state_directory=Path(tmp),
                poll_interval_seconds=0.01,
                sleeper=sleeps.append,
            )
            summary = runner.run_forever(max_ticks=2)
            self.assertEqual(summary["status"], "COMPLETED")
            self.assertEqual(summary["processed"], 1)
            heartbeat = json.loads((Path(tmp) / "heartbeat.json").read_text(encoding="utf-8"))
            result = json.loads((Path(tmp) / "last_result.json").read_text(encoding="utf-8"))
            self.assertEqual(heartbeat["status"], "COMPLETED")
            self.assertEqual(result["task_id"], "task-1")
            self.assertEqual(len(sleeps), 1)

    def test_stop_request_exits_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = NavigatorServiceRunner(
                loop=_SequenceLoop([None]),
                state_directory=Path(tmp),
                poll_interval_seconds=0,
            )
            runner.request_stop()
            summary = runner.run_forever()
            self.assertEqual(summary["status"], "STOPPED")
            self.assertEqual(summary["ticks"], 0)

    def test_transient_error_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = NavigatorServiceRunner(
                loop=_SequenceLoop([
                    RuntimeError("temporary"),
                    NavigatorResult("task-2", "SUCCESS", {}),
                ]),
                state_directory=Path(tmp),
                poll_interval_seconds=0,
                max_consecutive_errors=2,
            )
            summary = runner.run_forever(max_ticks=2)
            self.assertEqual(summary["processed"], 1)
            error = json.loads((Path(tmp) / "last_error.json").read_text(encoding="utf-8"))
            self.assertEqual(error["message"], "temporary")

    def test_stops_after_consecutive_error_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = NavigatorServiceRunner(
                loop=_SequenceLoop([RuntimeError("a"), RuntimeError("b")]),
                state_directory=Path(tmp),
                poll_interval_seconds=0,
                max_consecutive_errors=2,
            )
            with self.assertRaisesRegex(ServiceRunnerError, "error limit"):
                runner.run_forever(max_ticks=2)
            heartbeat = json.loads((Path(tmp) / "heartbeat.json").read_text(encoding="utf-8"))
            self.assertEqual(heartbeat["status"], "STOPPED_ERROR_LIMIT")


if __name__ == "__main__":
    unittest.main()
