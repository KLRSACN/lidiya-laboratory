from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ModelReply, TaskEnvelope


class ModelAdapter(ABC):
    """所有模型必須實作的相容端口。"""

    @abstractmethod
    def generate(self, task: TaskEnvelope, prompt: str) -> ModelReply:
        raise NotImplementedError

    def health_check(self) -> bool:
        return True


class MockAdapter(ModelAdapter):
    """第一階段測試用，不連接外部模型。"""

    def generate(self, task: TaskEnvelope, prompt: str) -> ModelReply:
        return ModelReply(
            message=f"ACK:{task.task_id}:{prompt}",
            completed=task.turn_count >= 1,
            evidence=["mock-adapter"],
        )
