from __future__ import annotations

import unittest

from completion import CompletionDetector
from contracts import CapturedResponse, ConversationState, OpeningMessage, Platform
from handoff import HandoffMetrics, HandoffPolicy, build_handoff_record


class ConversationBridgeP2Tests(unittest.TestCase):
    def test_opening_message_contains_completion_marker(self) -> None:
        message = OpeningMessage(
            mission_id="SHORTS-001",
            platform=Platform.CHATGPT,
            role="線上璃蒂雅",
            objective="規劃一分鐘短影音",
            current_state="尚未開始",
            requested_output=["趨勢方向", "60秒腳本"],
        ).render()
        self.assertIn("LIDIYA_TASK_COMPLETE", message)
        self.assertIn("SHORTS-001", message)

    def test_active_generation_waits(self) -> None:
        decision = CompletionDetector().decide(
            CapturedResponse(platform=Platform.CHATGPT, text="partial", generation_active=True)
        )
        self.assertEqual(decision.state, ConversationState.WAITING)

    def test_stable_marker_completes(self) -> None:
        decision = CompletionDetector().decide(
            CapturedResponse(
                platform=Platform.GEMINI,
                text="result\nLIDIYA_TASK_COMPLETE",
                stable_samples=2,
            )
        )
        self.assertEqual(decision.state, ConversationState.COMPLETE)

    def test_stable_without_marker_continues(self) -> None:
        decision = CompletionDetector().decide(
            CapturedResponse(platform=Platform.CHATGPT, text="result", stable_samples=2)
        )
        self.assertTrue(decision.should_continue)

    def test_handoff_threshold(self) -> None:
        policy = HandoffPolicy()
        metrics = HandoffMetrics(
            turns=20,
            estimated_context_ratio=0.4,
            changed_files=2,
            commits_since_checkpoint=2,
            unresolved_incidents=0,
        )
        self.assertTrue(policy.required(metrics))
        self.assertIn("turn_limit", policy.reasons(metrics))

    def test_handoff_record_preserves_generation(self) -> None:
        record = build_handoff_record(
            mission_id="SHORTS-001",
            generation=3,
            summary="短影音自主程序開發中",
            completed=["P2 contract"],
            pending=["Windows UI driver"],
            evidence=["CI"],
            next_opening="讀取交接後繼續",
        )
        self.assertEqual(record["generation"], 3)
        self.assertTrue(record["required_reads"])


if __name__ == "__main__":
    unittest.main()
