from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    decision: str
    target: str
    goal: str
    expected_state: str
    wake_after_seconds: int = 5

    def to_relay_text(self, mission_id: str) -> str:
        payload = {
            "mission_id": mission_id,
            "goal": self.goal,
            "expected_state": self.expected_state,
        }
        return "\n".join(
            [
                "[RELAY_READY]",
                f"[TARGET:{self.target}]",
                "[ACTION:SEND]",
                f"[WAKE_AFTER:{self.wake_after_seconds}]",
                "",
                "[RELAY_OUTPUT_BEGIN]",
                json.dumps(payload, ensure_ascii=False, indent=2),
                "[RELAY_OUTPUT_END]",
            ]
        )


def decide(worker_state: str) -> Decision:
    state = worker_state.strip().upper()
    if state.startswith("BUILDER_") and ("REPAIRED" in state or "PUBLISHED" in state):
        return Decision(
            decision="DISPATCH",
            target="WINDOW-02",
            goal="審查 Builder 最新成果並回傳 REVIEW_COMPLETED 或 NEEDS_CORRECTION",
            expected_state="REVIEW_COMPLETED",
        )
    if "REVIEW_COMPLETED" in state or "CONTINUITY_APPROVED" in state:
        return Decision(
            decision="DISPATCH",
            target="WINDOW-01",
            goal="依審查結果繼續下一個開發步驟",
            expected_state="BUILDER_TASK_COMPLETED",
        )
    if "BLOCKED" in state or "NEEDS_CORRECTION" in state:
        return Decision(
            decision="DISPATCH",
            target="WINDOW-01",
            goal="分析阻塞原因，採最小修正後重新回報",
            expected_state="BUILDER_CORRECTION_COMPLETED",
        )
    return Decision(
        decision="DISPATCH",
        target="WINDOW-01",
        goal="執行目前 Mission 的下一個最小可驗證工作",
        expected_state="BUILDER_TASK_COMPLETED",
    )
