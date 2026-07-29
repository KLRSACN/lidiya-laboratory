from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from agent_runtime import HomeBridgeAgentRuntime


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def due(schedule: str, last_run_at: str | None) -> bool:
    if schedule == "@hourly":
        if not last_run_at:
            return True
        last = datetime.fromisoformat(last_run_at)
        return (now_utc() - last).total_seconds() >= 3600
    if schedule == "@daily":
        if not last_run_at:
            return True
        last = datetime.fromisoformat(last_run_at)
        return (now_utc() - last).total_seconds() >= 86400
    return False


def run_due(root: Path) -> list[dict[str, object]]:
    runtime = HomeBridgeAgentRuntime(root)
    runtime.init()
    results: list[dict[str, object]] = []
    with sqlite3.connect(runtime.db_path) as conn:
        rows = conn.execute(
            "SELECT id, skill, schedule, arguments_json, last_run_at FROM cron_jobs WHERE enabled = 1"
        ).fetchall()
        for job_id, skill, schedule, arguments_json, last_run_at in rows:
            if not due(schedule, last_run_at):
                continue
            result = runtime.run_task(
                goal=f"cron:{job_id}",
                skill_name=skill,
                arguments=json.loads(arguments_json),
            )
            conn.execute(
                "UPDATE cron_jobs SET last_run_at = ? WHERE id = ?",
                (now_utc().isoformat(), job_id),
            )
            results.append({"job_id": job_id, "result": result})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    results = run_due(Path(args.root))
    print(json.dumps({"status": "CRON_TICK_COMPLETE", "jobs": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
