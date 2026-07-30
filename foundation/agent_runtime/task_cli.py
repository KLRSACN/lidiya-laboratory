from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from task_queue import PersistentTaskQueue, TaskQueueError


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("value must be a JSON object")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lidiya Navigator task control")
    parser.add_argument("--root", required=True, help="Navigator runtime root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit = subparsers.add_parser("submit", help="submit a durable task")
    submit.add_argument("--title", required=True)
    submit.add_argument("--goal", required=True)
    submit.add_argument("--skill", required=True)
    submit.add_argument("--arguments", type=_json_object, default={})
    submit.add_argument("--priority", type=int, default=100)
    submit.add_argument("--max-attempts", type=int, default=3)
    submit.add_argument("--requires-approval", action="store_true")

    list_parser = subparsers.add_parser("list", help="list tasks")
    list_parser.add_argument("--status")
    list_parser.add_argument("--limit", type=int, default=20)

    show = subparsers.add_parser("show", help="show one task and its events")
    show.add_argument("task_id")

    approve = subparsers.add_parser("approve", help="approve a waiting task")
    approve.add_argument("task_id")

    return parser


def _queue(root: Path) -> PersistentTaskQueue:
    return PersistentTaskQueue(root.resolve() / "navigator_tasks.db")


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root)
    queue = _queue(root)

    if args.command == "submit":
        metadata = {
            "skill_name": args.skill,
            "arguments": args.arguments,
        }
        task = queue.enqueue(
            title=args.title,
            goal=args.goal,
            priority=args.priority,
            max_attempts=args.max_attempts,
            requires_approval=args.requires_approval,
            metadata=metadata,
        )
        return {"command": "submit", "task": asdict(task)}

    if args.command == "list":
        tasks = queue.list_tasks(status=args.status, limit=args.limit)
        return {"command": "list", "tasks": [asdict(task) for task in tasks]}

    if args.command == "show":
        task = queue.get(args.task_id)
        return {
            "command": "show",
            "task": asdict(task),
            "events": queue.events(args.task_id),
        }

    if args.command == "approve":
        task = queue.approve(args.task_id)
        return {"command": "approve", "task": asdict(task)}

    raise TaskQueueError(f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_command(args)
    except TaskQueueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
