from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_escalator import HermesEscalator
from supervisor_adapter import HermesSupervisorAdapter
from task_queue import PersistentTaskQueue


class HermesEscalatorTests(unittest.TestCase):
    def _task(self, root: Path):
        queue = PersistentTaskQueue(root / "tasks.db")
        return queue.enqueue(title="demo", goal="repair failed copy")

    def test_valid_retry_plan_is_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = HermesSupervisorAdapter(
                root=root,
                allowed_tools=["fs.copy"],
                transport=lambda _endpoint, _payload, _timeout: {
                    "message": {
                        "content": (
                            '{"diagnosis":"destination missing","retry":true,'
                            '"steps":[{"tool":"fs.copy","arguments":'
                            '{"source":"workspace/inbox/a.txt",'
                            '"destination":"workspace/backup/a.txt"}}],'
                            '"notes":"retry once"}'
                        )
                    }
                },
            )
            result = HermesEscalator(adapter)(self._task(root), RuntimeError("copy failed"))
            self.assertTrue(result["retry"])
            self.assertFalse(result["requires_approval"])
            self.assertEqual(result["steps"][0]["tool"], "fs.copy")

    def test_stop_plan_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = HermesSupervisorAdapter(
                root=root,
                allowed_tools=["fs.copy"],
                transport=lambda _endpoint, _payload, _timeout: {
                    "message": {
                        "content": (
                            '{"diagnosis":"unsafe ambiguity","retry":false,'
                            '"steps":[],"notes":"manual review"}'
                        )
                    }
                },
            )
            result = HermesEscalator(adapter)(self._task(root), RuntimeError("ambiguous"))
            self.assertFalse(result["retry"])
            self.assertTrue(result["requires_approval"])

    def test_invalid_supervisor_response_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = HermesSupervisorAdapter(
                root=root,
                allowed_tools=["fs.copy"],
                transport=lambda _endpoint, _payload, _timeout: {
                    "message": {"content": "not-json"}
                },
            )
            result = HermesEscalator(adapter)(self._task(root), RuntimeError("failure"))
            self.assertFalse(result["retry"])
            self.assertTrue(result["requires_approval"])
            self.assertEqual(result["reason"], "supervisor_error")


if __name__ == "__main__":
    unittest.main()
