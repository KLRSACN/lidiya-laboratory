#!/usr/bin/env python3
"""Crash helper used by the independent auditor.

Runs an external claim command, waits until a durable marker exists, then kills
that process. The Builder command is supplied later; no Builder code is copied.
"""
from __future__ import annotations
import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command:
        print("missing command", file=sys.stderr)
        return 2
    proc = subprocess.Popen(args.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline and proc.poll() is None:
        if args.marker.exists():
            if os.name == "nt":
                proc.kill()
            else:
                os.kill(proc.pid, signal.SIGKILL)
            out, err = proc.communicate(timeout=5)
            print(f"CRASH_INJECTED pid={proc.pid} marker={args.marker}")
            print(out, end="")
            print(err, end="", file=sys.stderr)
            return 0
        time.sleep(0.02)
    proc.kill()
    out, err = proc.communicate()
    print(out, end="")
    print(err, end="", file=sys.stderr)
    print("marker not observed before timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
