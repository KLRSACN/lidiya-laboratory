from __future__ import annotations
import json, os, tempfile, subprocess, sys
from pathlib import Path

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

def write_json(path: Path, value):
    atomic_write(path, (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))

def main(base_dir: str) -> int:
    base = Path(base_dir).resolve()
    runtime = base / "runtime"
    trigger = base / "trigger.json"
    response = base / "response.txt"
    subprocess.run([sys.executable, str(base/"local_trigger.py"), str(trigger), str(runtime)], check=True)
    inbox_files = list((runtime/"inbox").glob("*.json"))
    if len(inbox_files) != 1:
        raise RuntimeError(f"expected one inbox task, got {len(inbox_files)}")
    inbox = inbox_files[0]
    task = json.loads(inbox.read_text(encoding="utf-8"))
    running = runtime/"running"/(inbox.stem + ".__owner__MANUAL-CONVERSATION.json")
    os.replace(inbox, running)
    request = {"opening_message": task["payload"]["opening_message"], "task_id": task["task_id"], "created_at": task["created_at"]}
    conversation_request = runtime/"home_staging"/"conversation_request.json"
    pending = runtime/"home_staging"/"pending_conversation.json"
    write_json(conversation_request, request)
    write_json(pending, {"status": "WAITING_MANUAL_RESPONSE", "task_id": task["task_id"], "conversation_request_file": str(conversation_request), "response_file": str(response)})
    if not response.exists():
        print("WAITING_FOR_RESPONSE")
        return 2
    subprocess.run([sys.executable, str(base/"manual_response_import.py"), str(runtime), str(running), str(response)], check=True)
    running.unlink(missing_ok=True)
    pending_data = json.loads(pending.read_text(encoding="utf-8"))
    pending_data["status"] = "COMPLETED"
    write_json(pending, pending_data)
    print("ROUNDTRIP_COMPLETE")
    return 0

if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1]))
