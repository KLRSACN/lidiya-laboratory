from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: dict[str, Any]
    error: str | None = None


class RuntimeErrorSafe(Exception):
    pass


class HomeBridgeAgentRuntime:
    def __init__(self, root: Path, config_path: Path | None = None) -> None:
        self.root = root.resolve()
        self.config_path = config_path or Path(__file__).with_name("runtime_config.json")
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.db_path = self.root / self.config["session_store"]
        self.skills_dir = self.root / self.config["skill_directory"]
        self.workspace = self.root / self.config["workspace_directory"]
        self.logs = self.root / self.config["log_directory"]
        self.quarantine = self.root / self.config["quarantine_directory"]
        self.tools: dict[str, Callable[[dict[str, Any]], ToolResult]] = {
            "fs.list": self._tool_list,
            "fs.mkdir": self._tool_mkdir,
            "fs.copy": self._tool_copy,
            "fs.move": self._tool_move,
            "fs.sha256": self._tool_sha256,
            "fs.write_text": self._tool_write_text,
        }

    def init(self) -> None:
        for path in (self.root, self.skills_dir, self.workspace, self.logs, self.quarantine):
            path.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    skill TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    tool TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    result_json TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    id TEXT PRIMARY KEY,
                    skill TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at TEXT
                );
                """
            )

    def run_task(self, goal: str, skill_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.init()
        skill = self._load_skill(skill_name)
        session_id = str(uuid.uuid4())
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions(id, goal, skill, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, goal, skill_name, "RUNNING", now, now),
            )

        context = {"goal": goal, "arguments": arguments, "session_id": session_id}
        max_steps = min(len(skill["steps"]), int(self.config["max_steps_per_session"]))

        try:
            for index, step in enumerate(skill["steps"][:max_steps]):
                rendered = self._render_arguments(step.get("arguments", {}), context)
                result = self._execute_step(session_id, index, step["tool"], rendered)
                context[f"step_{index}"] = result.output
                if not result.ok:
                    raise RuntimeErrorSafe(result.error or "tool failed")
            self._set_session_status(session_id, "SUCCESS")
            return {"session_id": session_id, "status": "SUCCESS", "context": context}
        except Exception as exc:
            self._set_session_status(session_id, "ESCALATE")
            return {
                "session_id": session_id,
                "status": "ESCALATE",
                "error": str(exc),
                "supervisor_model": self.config["supervisor_model"],
                "context": context,
            }

    def _execute_step(self, session_id: str, index: int, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        if tool_name not in self.config["allowed_tools"]:
            raise RuntimeErrorSafe(f"tool not allowed: {tool_name}")
        tool = self.tools.get(tool_name)
        if tool is None:
            raise RuntimeErrorSafe(f"tool not registered: {tool_name}")

        created_at = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO attempts(session_id, step_index, tool, arguments_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, index, tool_name, json.dumps(arguments, ensure_ascii=False), "RUNNING", created_at),
            )
            attempt_id = cursor.lastrowid

        try:
            result = tool(arguments)
        except Exception as exc:
            result = ToolResult(False, {}, str(exc))

        with self._connect() as conn:
            conn.execute(
                "UPDATE attempts SET result_json = ?, status = ? WHERE id = ?",
                (
                    json.dumps({"output": result.output, "error": result.error}, ensure_ascii=False),
                    "SUCCESS" if result.ok else "FAILED",
                    attempt_id,
                ),
            )
        return result

    def _load_skill(self, name: str) -> dict[str, Any]:
        path = self.skills_dir / f"{name}.json"
        if not path.exists():
            bundled = Path(__file__).with_name("skills") / f"{name}.json"
            if bundled.exists():
                self.skills_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bundled, path)
        if not path.exists():
            raise RuntimeErrorSafe(f"skill not found: {name}")
        skill = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(skill.get("steps"), list) or not skill["steps"]:
            raise RuntimeErrorSafe(f"invalid skill: {name}")
        return skill

    def _resolve_safe(self, value: str) -> Path:
        candidate = Path(value)
        path = candidate.resolve() if candidate.is_absolute() else (self.root / candidate).resolve()
        if path != self.root and self.root not in path.parents:
            raise RuntimeErrorSafe(f"path outside autonomous zone: {value}")
        return path

    def _render_arguments(self, value: Any, context: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {k: self._render_arguments(v, context) for k, v in value.items()}
        if isinstance(value, list):
            return [self._render_arguments(v, context) for v in value]
        if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
            keys = value[2:-2].strip().split(".")
            current: Any = context
            for key in keys:
                current = current[key]
            return current
        return value

    def _tool_list(self, args: dict[str, Any]) -> ToolResult:
        path = self._resolve_safe(str(args["path"]))
        if not path.exists() or not path.is_dir():
            return ToolResult(False, {}, f"directory not found: {path}")
        items = [{"name": p.name, "is_dir": p.is_dir(), "size": p.stat().st_size if p.is_file() else None} for p in path.iterdir()]
        return ToolResult(True, {"path": str(path), "items": items})

    def _tool_mkdir(self, args: dict[str, Any]) -> ToolResult:
        path = self._resolve_safe(str(args["path"]))
        path.mkdir(parents=True, exist_ok=True)
        return ToolResult(True, {"path": str(path), "exists": path.exists()})

    def _tool_copy(self, args: dict[str, Any]) -> ToolResult:
        source = self._resolve_safe(str(args["source"]))
        destination = self._resolve_safe(str(args["destination"]))
        if not source.exists():
            return ToolResult(False, {}, f"source not found: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)
        return ToolResult(True, {"source": str(source), "destination": str(destination), "verified": destination.exists()})

    def _tool_move(self, args: dict[str, Any]) -> ToolResult:
        source = self._resolve_safe(str(args["source"]))
        destination = self._resolve_safe(str(args["destination"]))
        if not source.exists():
            return ToolResult(False, {}, f"source not found: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return ToolResult(True, {"source": str(source), "destination": str(destination), "verified": destination.exists()})

    def _tool_sha256(self, args: dict[str, Any]) -> ToolResult:
        path = self._resolve_safe(str(args["path"]))
        if not path.is_file():
            return ToolResult(False, {}, f"file not found: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return ToolResult(True, {"path": str(path), "sha256": digest.hexdigest()})

    def _tool_write_text(self, args: dict[str, Any]) -> ToolResult:
        path = self._resolve_safe(str(args["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(args.get("content", "")), encoding="utf-8")
        return ToolResult(True, {"path": str(path), "bytes": path.stat().st_size})

    def _set_session_status(self, session_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?", (status, self._now(), session_id))

    def _connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("demo")
    run = sub.add_parser("run")
    run.add_argument("--goal", required=True)
    run.add_argument("--skill", required=True)
    run.add_argument("--arguments", default="{}")
    args = parser.parse_args(argv)

    runtime = HomeBridgeAgentRuntime(Path(args.root))
    if args.command == "init":
        runtime.init()
        print(json.dumps({"status": "INITIALIZED", "root": str(runtime.root)}, ensure_ascii=False))
        return 0
    if args.command == "demo":
        runtime.init()
        inbox = runtime.workspace / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "demo.txt").write_text("Lidiya Agent Runtime", encoding="utf-8")
        result = runtime.run_task(
            "copy approved demo file",
            "safe_file_copy",
            {"source": "workspace/inbox/demo.txt", "destination": "workspace/backup/demo.txt"},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "SUCCESS" else 1
    result = runtime.run_task(args.goal, args.skill, json.loads(args.arguments))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
