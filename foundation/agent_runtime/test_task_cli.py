from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from task_cli import _json_object, run_command
from task_queue import PersistentTaskQueue


class TaskCliTests(unittest.TestCase):
    def test_submit_creates_durable_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                root=tmp,
                command="submit",
                title="copy demo",
                goal="copy approved demo file",
                skill="safe_file_copy",
                arguments={
                    "source": "workspace/inbox/demo.txt",
                    "destination": "workspace/backup/demo.txt",
                },
                priority=10,
                max_attempts=2,
                requires_approval=False,
            )
            result = run_command(args)
            task = result["task"]
            self.assertEqual(task["status"], "RECEIVED")
            self.assertEqual(task["metadata"]["skill_name"], "safe_file_copy")
            queue = PersistentTaskQueue(Path(tmp) / "navigator_tasks.db")
            stored = queue.get(task["task_id"])
            self.assertEqual(stored.priority, 10)

    def test_list_filters_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "navigator_tasks.db")
            queue.enqueue(title="one", goal="first")
            second = queue.enqueue(title="two", goal="second")
            queue.transition(second.task_id, "FAILED")
            args = argparse.Namespace(root=tmp, command="list", status="FAILED", limit=20)
            result = run_command(args)
            self.assertEqual(len(result["tasks"]), 1)
            self.assertEqual(result["tasks"][0]["status"], "FAILED")

    def test_show_returns_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "navigator_tasks.db")
            task = queue.enqueue(title="one", goal="first")
            args = argparse.Namespace(root=tmp, command="show", task_id=task.task_id)
            result = run_command(args)
            self.assertEqual(result["task"]["task_id"], task.task_id)
            self.assertGreaterEqual(len(result["events"]), 1)

    def test_approve_waiting_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = PersistentTaskQueue(Path(tmp) / "navigator_tasks.db")
            task = queue.enqueue(title="formal", goal="activate", requires_approval=True)
            queue.transition(task.task_id, "WAITING_APPROVAL")
            args = argparse.Namespace(root=tmp, command="approve", task_id=task.task_id)
            result = run_command(args)
            self.assertEqual(result["task"]["status"], "PLANNED")

    def test_json_object_rejects_non_object(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            _json_object("[1,2,3]")


if __name__ == "__main__":
    unittest.main()
