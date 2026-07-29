from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from navigator_service_main import _planner, _verifier, build_service
from task_queue import TaskRecord


class NavigatorServiceMainTests(unittest.TestCase):
    def test_planner_requires_skill_metadata(self) -> None:
        task = TaskRecord(
            task_id="t1",
            title="x",
            goal="x",
            status="RECEIVED",
            priority=100,
            attempts=0,
            max_attempts=3,
            requires_approval=False,
            created_at="now",
            updated_at="now",
            metadata={},
        )
        with self.assertRaisesRegex(ValueError, "skill_name"):
            _planner(task)

    def test_planner_returns_skill_and_arguments(self) -> None:
        task = TaskRecord(
            task_id="t2",
            title="copy",
            goal="copy file",
            status="RECEIVED",
            priority=100,
            attempts=0,
            max_attempts=3,
            requires_approval=False,
            created_at="now",
            updated_at="now",
            metadata={"skill_name": "safe_file_copy", "arguments": {"a": 1}},
        )
        self.assertEqual(
            _planner(task),
            {"skill_name": "safe_file_copy", "arguments": {"a": 1}},
        )

    def test_build_service_creates_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = build_service(root, poll_interval_seconds=0)
            self.assertEqual(service.state_directory, (root / "navigator_state").resolve())
            self.assertTrue((root / "navigator_tasks.db").exists())
            self.assertTrue((root / "runtime.db").exists())

    def test_verifier_accepts_only_success(self) -> None:
        self.assertTrue(_verifier(None, {"status": "SUCCESS"}))  # type: ignore[arg-type]
        self.assertFalse(_verifier(None, {"status": "ESCALATE"}))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
