from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_runtime import HomeBridgeAgentRuntime
from recovery_executor import RecoveryExecutionError, RecoveryPlanExecutor


class RecoveryPlanExecutorTests(unittest.TestCase):
    def test_executes_validated_plan_and_persists_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = HomeBridgeAgentRuntime(root)
            runtime.init()
            source = root / "workspace" / "inbox" / "a.txt"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("hello", encoding="utf-8")

            executor = RecoveryPlanExecutor(runtime)
            result = executor.execute(
                task_id="task-1",
                goal="recover copy",
                steps=[
                    {
                        "tool": "fs.copy",
                        "arguments": {
                            "source": "workspace/inbox/a.txt",
                            "destination": "workspace/backup/a.txt",
                        },
                    },
                    {
                        "tool": "fs.sha256",
                        "arguments": {"path": "workspace/backup/a.txt"},
                    },
                ],
            )

            self.assertEqual(result.status, "SUCCESS")
            self.assertEqual(len(result.outputs), 2)
            with runtime._connect() as connection:
                attempts = connection.execute(
                    "SELECT COUNT(*) AS count FROM attempts WHERE session_id = ?",
                    (result.session_id,),
                ).fetchone()["count"]
            self.assertEqual(attempts, 2)

    def test_blocks_unregistered_tool_through_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = HomeBridgeAgentRuntime(Path(tmp))
            executor = RecoveryPlanExecutor(runtime)
            with self.assertRaisesRegex(RecoveryExecutionError, "tool not allowed"):
                executor.execute(
                    task_id="task-2",
                    goal="bad tool",
                    steps=[{"tool": "shell.exec", "arguments": {}}],
                )

    def test_failed_step_marks_session_escalate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = HomeBridgeAgentRuntime(Path(tmp))
            executor = RecoveryPlanExecutor(runtime)
            with self.assertRaisesRegex(RecoveryExecutionError, "source not found"):
                executor.execute(
                    task_id="task-3",
                    goal="missing source",
                    steps=[
                        {
                            "tool": "fs.copy",
                            "arguments": {
                                "source": "workspace/missing.txt",
                                "destination": "workspace/backup/a.txt",
                            },
                        }
                    ],
                )
            with runtime._connect() as connection:
                row = connection.execute(
                    "SELECT status FROM sessions ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
            self.assertEqual(row["status"], "ESCALATE")

    def test_enforces_max_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = HomeBridgeAgentRuntime(Path(tmp))
            executor = RecoveryPlanExecutor(runtime, max_steps=1)
            with self.assertRaisesRegex(RecoveryExecutionError, "exceeds max_steps"):
                executor.execute(
                    task_id="task-4",
                    goal="too many",
                    steps=[
                        {"tool": "fs.mkdir", "arguments": {"path": "workspace/a"}},
                        {"tool": "fs.mkdir", "arguments": {"path": "workspace/b"}},
                    ],
                )


if __name__ == "__main__":
    unittest.main()
