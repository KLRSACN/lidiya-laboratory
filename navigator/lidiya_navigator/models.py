from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WakeState(str, Enum):
    SLEEPING = "sleeping"
    WAKING = "waking"
    LOADING_CONTEXT = "loading_context"
    THINKING = "thinking"
    WAITING_REPLY = "waiting_reply"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    PAUSED = "paused"
    QUARANTINED = "quarantined"
    FAILED = "failed"


@dataclass(slots=True)
class TaskEnvelope:
    task_id: str
    goal: str
    completion_criteria: list[str]
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    max_turns: int = 8
    turn_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModelReply:
    message: str
    completed: bool = False
    requested_action: str | None = None
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WakeEvent:
    event_type: str
    source: str
    task_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    trust_level: str = "unverified"
