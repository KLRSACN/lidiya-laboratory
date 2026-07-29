from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from supervisor_adapter import HermesSupervisorAdapter, SupervisorError


class HermesSupervisorAdapterTests(unittest.TestCase):
    def test_accepts_bounded_relative_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = HermesSupervisorAdapter(
                root=Path(tmp),
                allowed_tools=["fs.copy", "fs.sha256"],
                transport=lambda _endpoint, _payload, _timeout: {
                    "message": {
                        "content": (
                            '{"diagnosis":"copy target was missing","retry":true,'
                            '"steps":[{"tool":"fs.copy","arguments":'
                            '{"source":"workspace/inbox/a.txt",'
                            '"destination":"workspace/backup/a.txt"}},'
                            '{"tool":"fs.sha256","arguments":'
                            '{"path":"workspace/backup/a.txt"}}],'
                            '"notes":"retry once"}'
                        )
                    }
                },
            )
            plan = adapter.propose({"status": "ESCALATE", "error": "missing target"})
            self.assertTrue(plan.retry)
            self.assertEqual(len(plan.steps), 2)
            self.assertEqual(plan.steps[0]["tool"], "fs.copy")

    def test_blocks_unlisted_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = HermesSupervisorAdapter(
                root=Path(tmp),
                allowed_tools=["fs.copy"],
                transport=lambda _endpoint, _payload, _timeout: {
                    "message": {
                        "content": (
                            '{"diagnosis":"run shell","retry":true,'
                            '"steps":[{"tool":"shell.exec","arguments":{}}],'
                            '"notes":""}'
                        )
                    }
                },
            )
            with self.assertRaisesRegex(SupervisorError, "tool not allowed"):
                adapter.propose({"status": "ESCALATE"})

    def test_blocks_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = HermesSupervisorAdapter(
                root=Path(tmp),
                allowed_tools=["fs.copy"],
                transport=lambda _endpoint, _payload, _timeout: {
                    "message": {
                        "content": (
                            '{"diagnosis":"copy outside","retry":true,'
                            '"steps":[{"tool":"fs.copy","arguments":'
                            '{"source":"workspace/a.txt",'
                            '"destination":"../outside.txt"}}],'
                            '"notes":""}'
                        )
                    }
                },
            )
            with self.assertRaisesRegex(SupervisorError, "outside autonomous zone"):
                adapter.propose({"status": "ESCALATE"})

    def test_retry_false_requires_no_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = HermesSupervisorAdapter(
                root=Path(tmp),
                allowed_tools=["fs.copy"],
                transport=lambda _endpoint, _payload, _timeout: {
                    "message": {
                        "content": (
                            '{"diagnosis":"stop","retry":false,'
                            '"steps":[{"tool":"fs.copy","arguments":{}}],'
                            '"notes":"manual review"}'
                        )
                    }
                },
            )
            with self.assertRaisesRegex(SupervisorError, "empty steps"):
                adapter.propose({"status": "ESCALATE"})


if __name__ == "__main__":
    unittest.main()
