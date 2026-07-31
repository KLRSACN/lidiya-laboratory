from __future__ import annotations
import hashlib, json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

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

def read_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def write_json(path: Path, value):
    atomic_write(path, (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))

def main(runtime_root: str, task_file: str, response_file: str) -> int:
    runtime = Path(runtime_root).resolve()
    task = read_json(Path(task_file).resolve())
    response_path = Path(response_file).resolve()
    response_text = response_path.read_text(encoding="utf-8")
    if not response_text.strip():
        raise ValueError("response.txt is empty")
    key = f"{task['mission_id']}::{task['token']}::{task['task_id']}"
    slug = f"{task['mission_id']}__{task['token']}__{task['task_id']}"
    outbox_path = runtime / "outbox" / f"{slug}.result.json"
    state_path = runtime / "state" / "dispatcher_state.json"
    journal_path = runtime / "state" / "journal" / f"{slug}.journal.json"
    result = {
        "status": "COMPLETED",
        "mission_id": task["mission_id"],
        "token": task["token"],
        "task_id": task["task_id"],
        "response_text": response_text,
        "response_sha256": hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
        "response_import_file": str(response_path),
        "outbox_path": str(outbox_path),
        "completed_at": now_iso()
    }
    journal = {"assignment_key": key, "phase": "PREPARED", "result": result, "updated_at": now_iso()}
    write_json(journal_path, journal)
    write_json(outbox_path, result)
    state = read_json(state_path) if state_path.exists() else {"completed_assignments": {}}
    state.setdefault("completed_assignments", {})[key] = result
    write_json(state_path, state)
    journal["phase"] = "COMMITTED"
    journal["updated_at"] = now_iso()
    write_json(journal_path, journal)
    print(outbox_path)
    return 0

if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
