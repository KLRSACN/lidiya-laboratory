from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_runtime import HomeBridgeAgentRuntime
from hermes_escalator import HermesEscalator
from navigator_loop import NavigatorLoop
from recovery_executor import RecoveryPlanExecutor
from service_runner import NavigatorServiceRunner
from supervisor_adapter import HermesSupervisorAdapter
from task_queue import PersistentTaskQueue, TaskRecord


def _planner(task: TaskRecord) -> dict[str, Any]:
    skill_name = task.metadata.get("skill_name")
    arguments = task.metadata.get("arguments", {})
    if not isinstance(skill_name, str) or not skill_name.strip():
        raise ValueError("task metadata.skill_name is required")
    if not isinstance(arguments, dict):
        raise ValueError("task metadata.arguments must be an object")
    return {"skill_name": skill_name.strip(), "arguments": arguments}


def _build_executor(runtime: HomeBridgeAgentRuntime):
    def _executor(task: TaskRecord, plan: dict[str, Any]) -> dict[str, Any]:
        result = runtime.run_task(
            goal=task.goal,
            skill_name=str(plan["skill_name"]),
            arguments=dict(plan.get("arguments", {})),
        )
        if result.get("status") != "SUCCESS":
            raise RuntimeError(str(result.get("error", "agent runtime escalated")))
        return result

    return _executor


def _verifier(_task: TaskRecord, execution: dict[str, Any]) -> bool:
    return execution.get("status") == "SUCCESS"


def build_service(root: Path, *, poll_interval_seconds: float = 5.0) -> NavigatorServiceRunner:
    root = root.resolve()
    runtime = HomeBridgeAgentRuntime(root)
    runtime.init()
    queue = PersistentTaskQueue(root / "navigator_tasks.db")

    adapter = HermesSupervisorAdapter(
        root=root,
        allowed_tools=list(runtime.config["allowed_tools"]),
        model=str(runtime.config.get("supervisor_model", "hermes3:latest")),
        endpoint=str(runtime.config.get("supervisor_endpoint", "http://127.0.0.1:11434/api/chat")),
        timeout_seconds=float(runtime.config.get("supervisor_timeout_seconds", 90)),
        max_plan_steps=int(runtime.config.get("supervisor_max_plan_steps", 6)),
    )
    recovery = RecoveryPlanExecutor(
        runtime,
        max_steps=int(runtime.config.get("supervisor_max_plan_steps", 6)),
    )

    def _recover(task: TaskRecord, escalation: dict[str, Any]) -> dict[str, Any]:
        result = recovery.execute(
            task_id=task.task_id,
            goal=task.goal,
            steps=list(escalation.get("steps", [])),
        )
        return {
            "status": result.status,
            "session_id": result.session_id,
            "outputs": result.outputs,
        }

    loop = NavigatorLoop(
        queue=queue,
        planner=_planner,
        executor=_build_executor(runtime),
        verifier=_verifier,
        escalator=HermesEscalator(adapter),
        recovery_executor=_recover,
    )
    return NavigatorServiceRunner(
        loop=loop,
        state_directory=root / "navigator_state",
        poll_interval_seconds=poll_interval_seconds,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Lidiya Navigator background service")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    state_path = args.root.resolve() / "navigator_state" / "heartbeat.json"
    if args.status:
        if not state_path.exists():
            print(json.dumps({"status": "NOT_STARTED"}, ensure_ascii=False))
            return 0
        print(state_path.read_text(encoding="utf-8"))
        return 0

    service = build_service(args.root, poll_interval_seconds=args.poll_seconds)
    service.install_signal_handlers()
    summary = service.run_forever(max_ticks=1 if args.once else None)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
