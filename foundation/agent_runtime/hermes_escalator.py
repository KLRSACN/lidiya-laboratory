from __future__ import annotations

from dataclasses import asdict
from typing import Any

from supervisor_adapter import HermesSupervisorAdapter, SupervisorError
from task_queue import TaskRecord


class HermesEscalator:
    """Adapts a validated Hermes supervisor plan to Navigator escalation output."""

    def __init__(self, adapter: HermesSupervisorAdapter) -> None:
        self.adapter = adapter

    def __call__(self, task: TaskRecord, exc: Exception) -> dict[str, Any]:
        escalation_input = {
            "status": "ESCALATE",
            "task": {
                "task_id": task.task_id,
                "title": task.title,
                "goal": task.goal,
                "status": task.status,
                "attempts": task.attempts,
                "max_attempts": task.max_attempts,
                "metadata": task.metadata,
            },
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }

        try:
            plan = self.adapter.propose(escalation_input)
        except SupervisorError as supervisor_error:
            return {
                "retry": False,
                "requires_approval": True,
                "reason": "supervisor_error",
                "error": str(supervisor_error),
            }

        result = asdict(plan)
        result["requires_approval"] = self._requires_approval(result)
        return result

    @staticmethod
    def _requires_approval(plan: dict[str, Any]) -> bool:
        if plan.get("retry") is False:
            return True
        notes = str(plan.get("notes", "")).lower()
        approval_markers = (
            "approval",
            "human review",
            "manual review",
            "正式版",
            "人工確認",
            "人工批准",
        )
        return any(marker in notes for marker in approval_markers)
