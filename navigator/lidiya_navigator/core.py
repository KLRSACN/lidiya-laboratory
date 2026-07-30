from __future__ import annotations

from dataclasses import asdict

from .adapters import ModelAdapter
from .guardian import Guardian
from .ledger import WakeLedger
from .models import ModelReply, TaskEnvelope, WakeEvent, WakeState


class Navigator:
    def __init__(self, adapter: ModelAdapter, guardian: Guardian, ledger: WakeLedger) -> None:
        self.adapter = adapter
        self.guardian = guardian
        self.ledger = ledger
        self.state = WakeState.SLEEPING

    def handle(self, event: WakeEvent, task: TaskEnvelope, prompt: str) -> ModelReply:
        self.state = WakeState.WAKING
        self.ledger.append("wake", task.task_id, {"event": asdict(event)})

        if event.task_id != task.task_id:
            self.state = WakeState.FAILED
            raise ValueError("event task_id does not match task")

        decision = self.guardian.inspect_text(prompt)
        if not decision.allowed:
            self.state = WakeState.QUARANTINED
            self.ledger.append("quarantine", task.task_id, {"reason": decision.reason})
            return ModelReply(message=decision.reason, completed=False)

        if task.turn_count >= task.max_turns:
            self.state = WakeState.PAUSED
            self.ledger.append("paused", task.task_id, {"reason": "max_turns reached"})
            return ModelReply(message="max_turns reached", completed=False)

        self.state = WakeState.THINKING
        task.turn_count += 1
        reply = self.adapter.generate(task, prompt)

        self.state = WakeState.VERIFYING
        reply_check = self.guardian.inspect_text(reply.message)
        if not reply_check.allowed:
            self.state = WakeState.QUARANTINED
            self.ledger.append("quarantine_reply", task.task_id, {"reason": reply_check.reason})
            return ModelReply(message=reply_check.reason, completed=False)

        self.state = WakeState.COMPLETED if reply.completed else WakeState.WAITING_REPLY
        self.ledger.append(
            "model_reply",
            task.task_id,
            {"completed": reply.completed, "turn_count": task.turn_count, "state": self.state.value},
        )
        return reply
