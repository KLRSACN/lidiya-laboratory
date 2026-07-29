from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from task_queue import PersistentTaskQueue, TaskQueueError, TaskRecord


class NavigatorError(Exception):
    pass


@dataclass(frozen=True)
class NavigatorResult:
    task_id: str
    status: str
    detail: dict[str, Any]


Planner = Callable[[TaskRecord], dict[str, Any]]
Executor = Callable[[TaskRecord, dict[str, Any]], dict[str, Any]]
Verifier = Callable[[TaskRecord, dict[str, Any]], bool]
Escalator = Callable[[TaskRecord, Exception], dict[str, Any]]


class NavigatorLoop:
    """Processes durable tasks one step at a time.

    This first version intentionally runs one bounded task per tick. A scheduler or
    Windows service may call tick repeatedly later. The loop owns state transitions
    but delegates planning, execution, verification, and escalation to injected
    collaborators so each layer remains testable and replaceable.
    """

    def __init__(
        self,
        *,
        queue: PersistentTaskQueue,
        planner: Planner,
        executor: Executor,
        verifier: Verifier,
        escalator: Escalator | None = None,
    ) -> None:
        self.queue = queue
        self.planner = planner
        self.executor = executor
        self.verifier = verifier
        self.escalator = escalator

    def tick(self) -> NavigatorResult | None:
        task = self._next_eligible_task()
        if task is None:
            return None

        if task.requires_approval:
            updated = self.queue.transition(task.task_id, "WAITING_APPROVAL")
            return NavigatorResult(updated.task_id, updated.status, {"reason": "approval_required"})

        try:
            planned = self.queue.transition(task.task_id, "PLANNED")
            plan = self.planner(planned)
            if not isinstance(plan, dict):
                raise NavigatorError("planner must return a dict")

            running = self.queue.transition(task.task_id, "RUNNING", payload={"plan": plan})
            execution = self.executor(running, plan)
            if not isinstance(execution, dict):
                raise NavigatorError("executor must return a dict")

            verifying = self.queue.transition(
                task.task_id,
                "VERIFYING",
                payload={"execution": execution},
            )
            passed = self.verifier(verifying, execution)
            if not isinstance(passed, bool):
                raise NavigatorError("verifier must return bool")

            if passed:
                success = self.queue.transition(
                    task.task_id,
                    "SUCCESS",
                    payload={"execution": execution},
                )
                return NavigatorResult(success.task_id, success.status, execution)

            return self._retry_or_fail(task, NavigatorError("verification failed"))
        except Exception as exc:
            return self._handle_failure(task, exc)

    def _next_eligible_task(self) -> TaskRecord | None:
        for status in ("RECEIVED", "RETRYING", "PLANNED"):
            tasks = self.queue.list_tasks(status=status, limit=1)
            if tasks:
                return tasks[0]
        return None

    def _handle_failure(self, task: TaskRecord, exc: Exception) -> NavigatorResult:
        if self.escalator is not None:
            try:
                escalation = self.escalator(task, exc)
            except Exception as escalation_error:
                return self._retry_or_fail(task, escalation_error)

            if not isinstance(escalation, dict):
                return self._retry_or_fail(task, NavigatorError("escalator must return a dict"))

            if escalation.get("requires_approval") is True:
                waiting = self.queue.transition(
                    task.task_id,
                    "WAITING_APPROVAL",
                    payload={"escalation": escalation},
                    last_error=str(exc),
                )
                return NavigatorResult(waiting.task_id, waiting.status, escalation)

            if escalation.get("retry") is False:
                failed = self.queue.transition(
                    task.task_id,
                    "FAILED",
                    payload={"escalation": escalation},
                    last_error=str(exc),
                )
                return NavigatorResult(failed.task_id, failed.status, escalation)

        return self._retry_or_fail(task, exc)

    def _retry_or_fail(self, task: TaskRecord, exc: Exception) -> NavigatorResult:
        updated = self.queue.transition(
            task.task_id,
            "RETRYING",
            last_error=str(exc),
            payload={"error": str(exc)},
        )
        return NavigatorResult(updated.task_id, updated.status, {"error": str(exc)})
