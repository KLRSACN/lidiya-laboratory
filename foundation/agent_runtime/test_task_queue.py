from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from task_queue import PersistentTaskQueue, TaskQueueError


class PersistentTaskQueueTests(unittest.TestCase):
    def test_enqueue_transition_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "tasks.db")
            task = queue.enqueue(title="Repair tool", goal="Fix and verify the tool")
            self.assertEqual(task.status, "RECEIVED")
            task = queue.transition(task.task_id, "PLANNED")
            task = queue.transition(task.task_id, "RUNNING")
            task = queue.transition(task.task_id, "VERIFYING")
            task = queue.transition(task.task_id, "SUCCESS")
            self.assertEqual(task.status, "SUCCESS")
            self.assertGreaterEqual(len(queue.events(task.task_id)), 5)

    def test_retry_limit_fails_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "tasks.db")
            task = queue.enqueue(
                title="Bounded retry",
                goal="Stop after retry bound",
                max_attempts=2,
            )
            task = queue.transition(task.task_id, "RETRYING", last_error="first")
            self.assertEqual(task.status, "RETRYING")
            self.assertEqual(task.attempts, 1)
            task = queue.transition(task.task_id, "RETRYING", last_error="second")
            self.assertEqual(task.status, "FAILED")
            self.assertEqual(task.attempts, 2)

    def test_approval_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "tasks.db")
            task = queue.enqueue(
                title="Activate release",
                goal="Switch active release",
                requires_approval=True,
            )
            task = queue.transition(task.task_id, "WAITING_APPROVAL")
            task = queue.approve(task.task_id)
            self.assertEqual(task.status, "PLANNED")
            self.assertFalse(task.requires_approval)

    def test_terminal_task_cannot_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "tasks.db")
            task = queue.enqueue(title="Done", goal="Finish")
            queue.transition(task.task_id, "SUCCESS")
            with self.assertRaisesRegex(TaskQueueError, "terminal"):
                queue.transition(task.task_id, "RUNNING")


if __name__ == "__main__":
    unittest.main()
