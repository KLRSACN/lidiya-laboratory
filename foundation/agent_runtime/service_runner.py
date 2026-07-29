from __future__ import annotations

import json
import signal
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from navigator_loop import NavigatorLoop, NavigatorResult


class ServiceRunnerError(Exception):
    pass


class NavigatorServiceRunner:
    """Continuously calls NavigatorLoop.tick() with bounded idle waiting.

    The runner is intentionally model-agnostic. It persists heartbeat and result
    snapshots so an operator can inspect progress without attaching to the process.
    """

    def __init__(
        self,
        *,
        loop: NavigatorLoop,
        state_directory: Path,
        poll_interval_seconds: float = 5.0,
        max_consecutive_errors: int = 5,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if poll_interval_seconds < 0:
            raise ServiceRunnerError("poll_interval_seconds must be non-negative")
        if max_consecutive_errors < 1:
            raise ServiceRunnerError("max_consecutive_errors must be at least 1")
        self.loop = loop
        self.state_directory = state_directory.resolve()
        self.poll_interval_seconds = poll_interval_seconds
        self.max_consecutive_errors = max_consecutive_errors
        self.sleeper = sleeper
        self.stop_requested = False
        self.state_directory.mkdir(parents=True, exist_ok=True)

    def request_stop(self) -> None:
        self.stop_requested = True

    def install_signal_handlers(self) -> None:
        def _handler(_signum: int, _frame: Any) -> None:
            self.request_stop()

        signal.signal(signal.SIGINT, _handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handler)

    def run_forever(self, *, max_ticks: int | None = None) -> dict[str, Any]:
        if max_ticks is not None and max_ticks < 1:
            raise ServiceRunnerError("max_ticks must be positive when provided")

        ticks = 0
        processed = 0
        consecutive_errors = 0
        last_result: dict[str, Any] | None = None
        self._write_heartbeat("STARTING", ticks=ticks, processed=processed)

        while not self.stop_requested:
            if max_ticks is not None and ticks >= max_ticks:
                break
            ticks += 1
            try:
                result = self.loop.tick()
                consecutive_errors = 0
                if result is not None:
                    processed += 1
                    last_result = self._serialize_result(result)
                    self._write_json_atomic(self.state_directory / "last_result.json", last_result)
                self._write_heartbeat(
                    "RUNNING",
                    ticks=ticks,
                    processed=processed,
                    last_result=last_result,
                )
            except Exception as exc:
                consecutive_errors += 1
                error_snapshot = {
                    "timestamp": self._now(),
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "consecutive_errors": consecutive_errors,
                }
                self._write_json_atomic(self.state_directory / "last_error.json", error_snapshot)
                self._write_heartbeat(
                    "DEGRADED",
                    ticks=ticks,
                    processed=processed,
                    error=error_snapshot,
                )
                if consecutive_errors >= self.max_consecutive_errors:
                    self._write_heartbeat(
                        "STOPPED_ERROR_LIMIT",
                        ticks=ticks,
                        processed=processed,
                        error=error_snapshot,
                    )
                    raise ServiceRunnerError("consecutive error limit reached") from exc

            if not self.stop_requested and (max_ticks is None or ticks < max_ticks):
                self.sleeper(self.poll_interval_seconds)

        final_status = "STOPPED" if self.stop_requested else "COMPLETED"
        summary = {
            "status": final_status,
            "ticks": ticks,
            "processed": processed,
            "last_result": last_result,
            "stopped_at": self._now(),
        }
        self._write_heartbeat(final_status, ticks=ticks, processed=processed, last_result=last_result)
        return summary

    @staticmethod
    def _serialize_result(result: NavigatorResult) -> dict[str, Any]:
        return {**asdict(result), "timestamp": NavigatorServiceRunner._now()}

    def _write_heartbeat(self, status: str, **extra: Any) -> None:
        payload = {"status": status, "timestamp": self._now(), **extra}
        self._write_json_atomic(self.state_directory / "heartbeat.json", payload)

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
