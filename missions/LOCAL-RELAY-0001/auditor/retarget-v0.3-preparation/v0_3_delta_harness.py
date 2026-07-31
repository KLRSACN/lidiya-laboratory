#!/usr/bin/env python3
"""Independent Local Relay v0.3 retarget harness.

This module defines process-based orchestration and assertions only. It does not
import Builder tests or assume Builder implementation names. A retarget binding
must provide the adapter contract operations.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def run_process(command: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = subprocess.run(command, text=True, capture_output=True, env=env, check=False)
    return {
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def simultaneous(commands: list[list[str]], barrier: Path) -> list[dict[str, Any]]:
    env = os.environ.copy()
    env["AUDITOR_PROCESS_BARRIER"] = str(barrier)
    processes = [
        subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        for cmd in commands
    ]
    barrier.write_text("GO\n", encoding="utf-8")
    results = []
    for cmd, proc in zip(commands, processes):
        stdout, stderr = proc.communicate(timeout=30)
        results.append({"command": cmd, "exit_code": proc.returncode, "stdout": stdout, "stderr": stderr})
    return results


def assert_generation_fencing(records: dict[str, Any]) -> None:
    assert records["claim_a"]["lease_generation"] == 1
    assert records["claim_b"]["lease_generation"] == 2
    assert records["a_heartbeat"]["accepted"] is False
    assert records["a_submit"]["accepted"] is False
    assert records["b_submit"]["accepted"] is True
    assert records["successful_commits"] == 1


def assert_recovery_monotonic(values: list[int]) -> None:
    assert values
    assert all(current > previous for previous, current in zip(values, values[1:]))


def assert_checkpoint_failure_state(report: dict[str, Any]) -> None:
    assert report["false_completion"] is False
    assert report["running_recoverable"] is True
    assert report["duplicate_side_effect"] is False


def create_isolated_runtime() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory(prefix="local_relay_v03_audit_")
    return temp, Path(temp.name) / "runtime"


def main() -> int:
    print(json.dumps({
        "status": "HARNESS_READY_PENDING_BUILDER_V0_3_BINDING",
        "process_based": True,
        "tests": [
            "lease_generation_fencing",
            "recovery_count_monotonic",
            "runtime_root_allowlist",
            "checkpoint_failure_recovery",
            "canonical_task_state",
            "completed_registry_outbox_path",
            "multiprocess_claim_submit_race",
            "manifest_integrity"
        ]
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
