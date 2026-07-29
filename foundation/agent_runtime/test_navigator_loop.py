from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from navigator_loop import NavigatorLoop
from task_queue import PersistentTaskQueue


class NavigatorLoopTests(unittest.TestCase):
    def test_successful_task_reaches_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "tasks.db")
            task = queue.enqueue(title="copy", goal="copy approved file")
            loop = NavigatorLoop(
                queue=queue,
                planner=lambda _task: {"steps": ["copy"]},
                executor=lambda _task, _plan: {"verified": True},
                verifier=lambda _task, result: bool(result["verified"]),
            )
            result = loop.tick()
            self.assertIsNotNone(result)
            self.assertEqual(result.status, "SUCCESS")
            self.assertEqual(queue.get(task.task_id).status, "SUCCESS")

    def test_required_approval_stops_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "tasks.db")
            task = queue.enqueue(
                title="activate",
                goal="activate release",
                requires_approval=True,
            )
            called = {"executor": False}
            loop = NavigatorLoop(
                queue=queue,
                planner=lambda _task: {},
                executor=lambda _task, _plan: called.__setitem__("executor", True) or {},
                verifier=lambda _task, _result: True,
            )
            result = loop.tick()
            self.assertEqual(result.status, "WAITING_APPROVAL")
            self.assertFalse(called["executor"])
            self.assertEqual(queue.get(task.task_id).status, "WAITING_APPROVAL")

    def test_failure_enters_retrying(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "tasks.db")
            task = queue.enqueue(title="broken", goal="run task", max_attempts=3)
            loop = NavigatorLoop(
                queue=queue,
                planner=lambda _task: {"steps": []},
                executor=lambda _task, _plan: (_ for _ in ()).throw(RuntimeError("boom")),
                verifier=lambda _task, _result: True,
            )
            result = loop.tick()
            self.assertEqual(result.status, "RETRYING")
            self.assertEqual(queue.get(task.task_id).attempts, 1)

    def test_escalator_can_require_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "tasks.db")
            task = queue.enqueue(title="formal change", goal="change formal release")
            loop = NavigatorLoop(
                queue=queue,
                planner=lambda _task: {"steps": []},
                executor=lambda _task, _plan: (_ for _ in ()).throw(RuntimeError("policy")),
                verifier=lambda _task, _result: True,
                escalator=lambda _task, _error: {
                    "requires_approval": True,
                    "reason": "formal release change",
                },
            )
            result = loop.tick()
            self.assertEqual(result.status, "WAITING_APPROVAL")
            self.assertEqual(queue.get(task.task_id).status, "WAITING_APPROVAL")


if __name__ == "__main__":
    unittest.main()
