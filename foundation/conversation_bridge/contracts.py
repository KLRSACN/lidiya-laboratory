from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Platform(str, Enum):
    CHATGPT = "chatgpt"
    GEMINI = "gemini"
    LOCAL = "local"


class ConversationState(str, Enum):
    READY = "ready"
    SENDING = "sending"
    WAITING = "waiting"
    CAPTURING = "capturing"
    COMPLETE = "complete"
    NEEDS_CONTINUE = "needs_continue"
    HANDOFF_REQUIRED = "handoff_required"
    FAILED = "failed"


@dataclass(slots=True)
class OpeningMessage:
    mission_id: str
    platform: Platform
    role: str
    objective: str
    current_state: str
    requested_output: list[str]
    completion_marker: str = "LIDIYA_TASK_COMPLETE"
    constraints: list[str] = field(default_factory=list)

    def render(self) -> str:
        outputs = "\n".join(f"- {item}" for item in self.requested_output)
        constraints = "\n".join(f"- {item}" for item in self.constraints) or "- 無額外限制"
        return (
            f"[LIDIYA MISSION {self.mission_id}]\n"
            f"角色：{self.role}\n"
            f"目標：{self.objective}\n"
            f"目前狀態：{self.current_state}\n"
            f"需要輸出：\n{outputs}\n"
            f"限制：\n{constraints}\n"
            f"完成時請在最後一行單獨輸出：{self.completion_marker}"
        )


@dataclass(slots=True)
class CapturedResponse:
    platform: Platform
    text: str
    stable_samples: int = 0
    generation_active: bool = False
    error_banner: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompletionDecision:
    state: ConversationState
    reason: str
    should_continue: bool
    should_handoff: bool = False
