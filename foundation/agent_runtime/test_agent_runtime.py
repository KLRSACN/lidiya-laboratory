from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_runtime import HomeBridgeAgentRuntime, RuntimeErrorSafe


class AgentRuntimeTests(unittest.TestCase):
    def test_demo_copy_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = HomeBridgeAgentRuntime(root)
            runtime.init()
            source = runtime.workspace / "inbox" / "a.txt"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("abc", encoding="utf-8")
            result = runtime.run_task(
                "copy",
                "safe_file_copy",
                {"source": "workspace/inbox/a.txt", "destination": "workspace/out/a.txt"},
            )
            self.assertEqual(result["status"], "SUCCESS")
            self.assertEqual((runtime.workspace / "out" / "a.txt").read_text(encoding="utf-8"), "abc")

    def test_scope_escape_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = HomeBridgeAgentRuntime(Path(tmp))
            runtime.init()
            with self.assertRaises(RuntimeErrorSafe):
                runtime._resolve_safe("..\\outside.txt")


if __name__ == "__main__":
    unittest.main()
