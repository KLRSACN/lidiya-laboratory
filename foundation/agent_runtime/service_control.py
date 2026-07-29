from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any


class ServiceControlError(Exception):
    pass


def _pid_path(root: Path) -> Path:
    return root.resolve() / "navigator_state" / "service.pid"


def _state_path(root: Path) -> Path:
    return root.resolve() / "navigator_state" / "heartbeat.json"


def _is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_pid(root: Path) -> int | None:
    path = _pid_path(root)
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def start_service(root: Path, *, poll_seconds: float = 5.0, python_executable: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    state_dir = root / "navigator_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    existing_pid = _read_pid(root)
    if existing_pid is not None and _is_running(existing_pid):
        raise ServiceControlError(f"service already running with pid {existing_pid}")

    python_executable = python_executable or sys.executable
    service_main = Path(__file__).with_name("navigator_service_main.py")
    stdout_path = state_dir / "service.stdout.log"
    stderr_path = state_dir / "service.stderr.log"
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    stdout_handle = stdout_path.open("a", encoding="utf-8")
    stderr_handle = stderr_path.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [
                python_executable,
                str(service_main),
                "--root",
                str(root),
                "--poll-seconds",
                str(poll_seconds),
            ],
            cwd=str(service_main.parent),
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=creationflags,
            close_fds=os.name != "nt",
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()

    _pid_path(root).write_text(str(process.pid), encoding="utf-8")
    return {
        "status": "STARTED",
        "pid": process.pid,
        "root": str(root),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }


def stop_service(root: Path) -> dict[str, Any]:
    root = root.resolve()
    pid = _read_pid(root)
    if pid is None:
        return {"status": "NOT_RUNNING"}
    if not _is_running(pid):
        _pid_path(root).unlink(missing_ok=True)
        return {"status": "STALE_PID_REMOVED", "pid": pid}

    try:
        if os.name == "nt":
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        raise ServiceControlError(f"failed to stop pid {pid}: {exc}") from exc

    return {"status": "STOP_SIGNAL_SENT", "pid": pid}


def status_service(root: Path) -> dict[str, Any]:
    root = root.resolve()
    pid = _read_pid(root)
    running = pid is not None and _is_running(pid)
    heartbeat: dict[str, Any] | None = None
    state_path = _state_path(root)
    if state_path.exists():
        try:
            heartbeat = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            heartbeat = {"status": "UNREADABLE"}
    return {
        "status": "RUNNING" if running else "STOPPED",
        "pid": pid,
        "heartbeat": heartbeat,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control the Lidiya Navigator background process")
    parser.add_argument("--root", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--poll-seconds", type=float, default=5.0)
    subparsers.add_parser("stop")
    subparsers.add_parser("status")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            result = start_service(args.root, poll_seconds=args.poll_seconds)
        elif args.command == "stop":
            result = stop_service(args.root)
        else:
            result = status_service(args.root)
    except ServiceControlError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
