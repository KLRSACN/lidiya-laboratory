from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from task_queue import PersistentTaskQueue, TaskRecord


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
RecoveryExecutor = Callable[[TaskRecord, dict[str, Any]], dict[str, Any]]


class NavigatorLoop:
    """Processes durable tasks one bounded task per tick.

    Planning, execution, verification, escalation, and recovery are injected so
    the Navigator remains testable. A validated supervisor plan may be passed to
    a bounded RecoveryPlanExecutor, but the Navigator never executes arbitrary
    natural-language instructions or shell commands.
    """

    def __init__(
        self,
        *,
        queue: PersistentTaskQueue,
        planner: Planner,
        executor: Executor,
        verifier: Verifier,
        escalator: Escalator | None = None,
        recovery_executor: RecoveryExecutor | None = None,
    ) -> None:
        self.queue = queue
        self.planner = planner
        self.executor = executor
        self.verifier = verifier
        self.escalator = escalator
        self.recovery_executor = recovery_executor

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
            return self._finish_verification(verifying, execution)
        except Exception as exc:
            return self._handle_failure(task, exc)

    def _finish_verification(
        self,
        task: TaskRecord,
        execution: dict[str, Any],
    ) -> NavigatorResult:
        passed = self.verifier(task, execution)
        if not isinstance(passed, bool):
            raise NavigatorError("verifier must return bool")
        if not passed:
            return self._handle_failure(task, NavigatorError("verification failed"))

        success = self.queue.transition(
            task.task_id,
            "SUCCESS",
            payload={"execution": execution},
        )
        return NavigatorResult(success.task_id, success.status, execution)

    def _next_eligible_task(self) -> TaskRecord | None:
        for status in ("RECEIVED", "RETRYING", "PLANNED"):
            tasks = self.queue.list_tasks(status=status, limit=1)
            if tasks:
                return tasks[0]
        return None

    def _handle_failure(self, task: TaskRecord, exc: Exception) -> NavigatorResult:
        if self.escalator is None:
            return self._retry_or_fail(task, exc)

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

        steps = escalation.get("steps")
        if escalation.get("retry") is True and isinstance(steps, list) and steps:
            if self.recovery_executor is None:
                return self._retry_or_fail(
                    task,
                    NavigatorError("validated recovery plan exists but no recovery executor configured"),
                )
            return self._execute_recovery(task, escalation, exc)

        return self._retry_or_fail(task, exc)

    def _execute_recovery(
        self,
        task: TaskRecord,
        escalation: dict[str, Any],
        original_error: Exception,
    ) -> NavigatorResult:
        try:
            recovering = self.queue.transition(
                task.task_id,
                "RETRYING",
                payload={"escalation": escalation},
                last_error=str(original_error),
            )
            if recovering.status == "FAILED":
                return NavigatorResult(
                    recovering.task_id,
                    recovering.status,
                    {"error": "retry limit reached", "escalation": escalation},
                )

            running = self.queue.transition(
                task.task_id,
                "RUNNING",
                payload={"recovery_plan": escalation},
            )
            recovery = self.recovery_executor(running, escalation)
            if not isinstance(recovery, dict):
                raise NavigatorError("recovery_executor must return a dict")

            verifying = self.queue.transition(
                task.task_id,
                "VERIFYING",
                payload={"recovery": recovery},
            )
            return self._finish_verification(verifying, recovery)
        except Exception as recovery_error:
            return self._retry_or_fail(task, recovery_error)

    def _retry_or_fail(self, task: TaskRecord, exc: Exception) -> NavigatorResult:
        current = self.queue.get(task.task_id)
        if current.status in {"SUCCESS", "FAILED", "CANCELLED"}:
            return NavigatorResult(current.task_id, current.status, {"error": str(exc)})
        updated = self.queue.transition(
            task.task_id,
            "RETRYING",
            last_error=str(exc),
            payload={"error": str(exc)},
        )
        return NavigatorResult(updated.task_id, updated.status, {"error": str(exc)})
