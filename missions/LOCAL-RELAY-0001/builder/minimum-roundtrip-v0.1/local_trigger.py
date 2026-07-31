from __future__ import annotations
import json, os, tempfile
from pathlib import Path

REQUIRED = {"mission_id","token","task_id","opening_message","created_at"}

def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

def main(trigger_file: str, runtime_root: str) -> int:
    trigger_path = Path(trigger_file).resolve()
    runtime = Path(runtime_root).resolve()
    with trigger_path.open("r", encoding="utf-8") as handle:
        trigger = json.load(handle)
    missing = REQUIRED - set(trigger)
    if missing:
        raise ValueError("missing fields: " + ",".join(sorted(missing)))
    inbox = runtime / "inbox" / f"{trigger['mission_id']}__{trigger['token']}__{trigger['task_id']}.json"
    task = {
        "mission_id": trigger["mission_id"],
        "token": trigger["token"],
        "task_id": trigger["task_id"],
        "target_worker": "MANUAL-CONVERSATION",
        "action": "REQUEST_CONVERSATION",
        "objective": "Prepare a manual conversation request and import the response.",
        "created_at": trigger["created_at"],
        "attempt": 0,
        "max_attempts": 1,
        "lease_seconds": 300,
        "payload": {"opening_message": trigger["opening_message"]},
        "success_criteria": ["conversation_request_created", "manual_response_imported"],
        "evidence_required": ["outbox_result", "completed_registry", "journal"]
    }
    atomic_write(inbox, (json.dumps(task, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(inbox)
    return 0

if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
