#!/usr/bin/env python3
"""Generate deterministic malformed packets for quarantine testing."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

BASE = {
    "mission_id": "LOCAL-RELAY-0001",
    "token": "RELAY-BOOTSTRAP-0001",
    "task_id": "TASK-001",
    "payload": {"value": 1},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    valid = dict(BASE)
    valid["payload_hash"] = hashlib.sha256(canonical(valid["payload"])).hexdigest()
    raw = json.dumps(valid, indent=2).encode()
    write(output / "truncated.json", raw[: len(raw) // 2])
    write(output / "non_json.json", b"not-json\n")
    packet = dict(valid)
    packet.pop("task_id")
    write(output / "missing_fields.json", json.dumps(packet).encode())
    packet = dict(valid)
    packet["task_id"] = ["wrong-type"]
    write(output / "wrong_types.json", json.dumps(packet).encode())
    packet = dict(valid)
    packet["payload_hash"] = "0" * 64
    write(output / "hash_mismatch.json", json.dumps(packet).encode())
    packet = dict(valid)
    packet["result_path"] = "../../escape.json"
    write(output / "path_traversal.json", json.dumps(packet).encode())
    write(output / "partial_packet.json.tmp", raw[: len(raw) // 2])
    print("GENERATED=7")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
