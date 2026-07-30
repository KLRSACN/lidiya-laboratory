from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from agent_runtime import HomeBridgeAgentRuntime, RuntimeErrorSafe


class RecoveryExecutionError(Exception):
    """Raised when a validated recovery plan cannot complete safely."""


@dataclass(frozen=True)
class RecoveryExecutionResult:
    session_id: str
    status: str
    outputs: list[dict[str, Any]]


class RecoveryPlanExecutor:
    """Executes an already policy-validated Hermes recovery plan.

    This is the execution bridge between Hermes and HomeBridgeAgentRuntime. It
    does not accept arbitrary prose or shell commands. Every step still passes
    through the runtime's registered-tool and allowed-tool checks, and each
    attempt is persisted in the existing SQLite session store.
    """

    def __init__(self, runtime: HomeBridgeAgentRuntime, *, max_steps: int = 6) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.runtime = runtime
        self.max_steps = max_steps

    def execute(
        self,
        *,
        task_id: str,
        goal: str,
        steps: list[dict[str, Any]],
    ) -> RecoveryExecutionResult:
        if not isinstance(steps, list):
            raise RecoveryExecutionError("steps must be a list")
        if not steps:
            raise RecoveryExecutionError("recovery plan has no steps")
        if len(steps) > self.max_steps:
            raise RecoveryExecutionError("recovery plan exceeds max_steps")

        self.runtime.init()
        session_id = str(uuid.uuid4())
        now = self.runtime._now()
        skill_name = f"hermes_recovery:{task_id}"

        with self.runtime._connect() as connection:
            connection.execute(
                "INSERT INTO sessions(id, goal, skill, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, goal, skill_name, "RUNNING", now, now),
            )

        outputs: list[dict[str, Any]] = []
        try:
            for index, step in enumerate(steps):
                if not isinstance(step, dict):
                    raise RecoveryExecutionError(f"step {index} must be an object")
                tool = step.get("tool")
                arguments = step.get("arguments", {})
                if not isinstance(tool, str) or not tool:
                    raise RecoveryExecutionError(f"step {index} missing tool")
                if not isinstance(arguments, dict):
                    raise RecoveryExecutionError(f"step {index} arguments must be an object")

                result = self.runtime._execute_step(session_id, index, tool, arguments)
                outputs.append(
                    {
                        "step_index": index,
                        "tool": tool,
                        "ok": result.ok,
                        "output": result.output,
                        "error": result.error,
                    }
                )
                if not result.ok:
                    raise RuntimeErrorSafe(result.error or f"recovery step {index} failed")

            self.runtime._set_session_status(session_id, "SUCCESS")
            return RecoveryExecutionResult(session_id, "SUCCESS", outputs)
        except Exception as exc:
            self.runtime._set_session_status(session_id, "ESCALATE")
            raise RecoveryExecutionError(str(exc)) from exc
