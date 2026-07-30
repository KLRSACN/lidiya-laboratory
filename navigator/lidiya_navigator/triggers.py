from __future__ import annotations

from typing import Any

from .models import WakeEvent


def completion_event(task_id: str, payload: dict[str, Any] | None = None) -> WakeEvent:
    return WakeEvent(
        event_type="MODEL_REPLY_COMPLETED",
        source="navigator",
        task_id=task_id,
        payload=dict(payload or {}),
        trust_level="internal",
    )
