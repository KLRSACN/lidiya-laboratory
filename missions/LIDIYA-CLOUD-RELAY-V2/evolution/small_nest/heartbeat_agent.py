from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

_THIS = Path(__file__).resolve()
_TOWER = _THIS.parents[1] / "local_command_tower"
if str(_TOWER) not in sys.path:
    sys.path.insert(0, str(_TOWER))

from heartbeat_engine import HeartbeatEngine, InvalidHeartbeatConfig


def run_once(
    *,
    state_path: str | Path,
    now: int,
    interval_seconds: int = 300,
    endpoint_probe: Optional[Callable[[], bool]] = None,
):
    engine = HeartbeatEngine(state_path, interval_seconds=interval_seconds)
    endpoint_ok = True if endpoint_probe is None else bool(endpoint_probe())
    return engine.tick(now=int(now), endpoint_ok=endpoint_ok)


def run_loop(
    *,
    state_path: str | Path,
    interval_seconds: int = 300,
    endpoint_probe: Optional[Callable[[], bool]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    clock_fn: Callable[[], float] = time.time,
) -> None:
    engine = HeartbeatEngine(state_path, interval_seconds=interval_seconds)
    while True:
        now = int(clock_fn())
        if engine.due(now):
            endpoint_ok = True if endpoint_probe is None else bool(endpoint_probe())
            result = engine.tick(now=now, endpoint_ok=endpoint_ok)
            if result.compact_required:
                print(json.dumps(engine.compact_record(), sort_keys=True), flush=True)
        sleep_for = max(1, min(interval_seconds, (engine.state.next_due_at or now + interval_seconds) - now))
        sleep_fn(float(sleep_for))


def main() -> int:
    parser = argparse.ArgumentParser(description="Lidiya Small-Nest bounded heartbeat agent")
    parser.add_argument("--state", default=".lidiya/heartbeat_state.json")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        if args.once:
            result = run_once(state_path=args.state, now=int(time.time()), interval_seconds=args.interval)
            print(json.dumps(result.__dict__, sort_keys=True))
            return 0
        run_loop(state_path=args.state, interval_seconds=args.interval)
        return 0
    except (InvalidHeartbeatConfig, OSError, ValueError) as exc:
        print(f"heartbeat_agent_error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
