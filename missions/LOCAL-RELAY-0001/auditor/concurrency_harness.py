#!/usr/bin/env python3
"""Independent process-based concurrency/fault harness.

The harness invokes a Builder-supplied CLI adapter. It deliberately does not
import or duplicate Builder tests. Adapter command examples are configured via
arguments after a Builder frozen commit exists.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, tempfile, time
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snap(root: Path):
    return {str(p.relative_to(root)): sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}


def atomic_claim_race(adapter: list[str], root: Path, packet: Path):
    barrier = root / "start.barrier"
    env = os.environ.copy()
    env["AUDIT_START_BARRIER"] = str(barrier)
    commands, procs = [], []
    for owner in ("AUDITOR-A", "AUDITOR-B"):
        cmd = adapter + ["claim", "--root", str(root), "--packet", str(packet), "--owner", owner]
        commands.append(cmd)
        procs.append(subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env))
    barrier.write_text("go", encoding="utf-8")
    results = []
    for proc, command in zip(procs, commands):
        out, err = proc.communicate(timeout=20)
        results.append({"command": command, "pid": proc.pid, "exit_code": proc.returncode, "stdout": out, "stderr": err})
    successes = sum(item["exit_code"] == 0 for item in results)
    return {"name": "atomic_claim_race", "pass": successes == 1, "successes": successes, "runs": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", nargs="+", required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"generated_at_monotonic": time.monotonic(), "tests": []}
    with tempfile.TemporaryDirectory(prefix="local_relay_audit_") as temp_dir:
        root = Path(temp_dir)
        packet = root / "inbox" / args.packet.name
        packet.parent.mkdir(parents=True)
        packet.write_bytes(args.packet.read_bytes())
        report["before"] = snap(root)
        report["tests"].append(atomic_claim_race(args.adapter, root, packet))
        report["after"] = snap(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"tests": len(report["tests"]), "passed": sum(test["pass"] for test in report["tests"])}, indent=2))
    return 0 if all(test["pass"] for test in report["tests"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
