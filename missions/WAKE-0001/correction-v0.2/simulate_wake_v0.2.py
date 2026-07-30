from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_TRIGGER_FIELDS = (
    "MISSION_ID", "TARGET", "ACTION", "TOKEN",
    "OBJECTIVE", "SUCCESS_CRITERIA", "EVIDENCE_REQUIRED",
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checkpoint_hash(checkpoint: dict[str, Any]) -> str:
    payload = {k: v for k, v in checkpoint.items() if k != "checkpoint_hash"}
    return sha256_bytes(canonical_json_bytes(payload))


def atomic_write_json(path: Path, value: dict[str, Any], *, refuse_overwrite: bool = False) -> None:
    if refuse_overwrite and path.exists():
        raise FileExistsError(f"refuse overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class RunResult:
    status: str
    state: str
    heartbeat: str
    progress_token: str | None
    result_hash: str | None
    events: list[str]
    executed_steps: list[str]
    blocker: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class WakeWorkerV02:
    """Persistent, deterministic Wake Mechanism v0.2 worker simulation."""

    def __init__(self, root: Path):
        self.root = root
        self.state_path = root / "wake_runtime_state.json"
        self.checkpoint_dir = root / "checkpoints"
        self.result_dir = root / "results"
        self.log_dir = root / "logs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(exist_ok=True)
        self.result_dir.mkdir(exist_ok=True)
        self.log_dir.mkdir(exist_ok=True)
        if not self.state_path.exists():
            atomic_write_json(self.state_path, {"completed_assignments": {}, "active_assignments": {}})

    @staticmethod
    def assignment_key(mission_id: str, token: str) -> str:
        return f"{mission_id}::{token}"

    @staticmethod
    def progress_value(token: str) -> int:
        try:
            return int(token.rsplit(":P", 1)[1])
        except Exception as exc:
            raise ValueError("invalid progress token") from exc

    @staticmethod
    def progress_token(mission_id: str, token: str, step: int) -> str:
        return f"{mission_id}:{token}:P{step:04d}"

    def validate_trigger(self, trigger: dict[str, Any]) -> tuple[bool, str]:
        missing = [name for name in REQUIRED_TRIGGER_FIELDS if not trigger.get(name)]
        if missing:
            return False, "INVALID_TRIGGER_MISSING_FIELDS:" + ",".join(missing)
        if trigger["TARGET"] != "WORKER-01":
            return False, "INVALID_TRIGGER_WRONG_TARGET"
        if trigger["ACTION"] != "START":
            return False, "INVALID_TRIGGER_WRONG_ACTION"
        return True, "VALID"

    def checkpoint_path(self, mission_id: str, token: str) -> Path:
        safe = self.assignment_key(mission_id, token).replace("::", "__")
        return self.checkpoint_dir / f"{safe}.json"

    def result_path(self, mission_id: str, token: str) -> Path:
        safe = self.assignment_key(mission_id, token).replace("::", "__")
        return self.result_dir / f"{safe}.json"

    def _save_checkpoint(self, cp: dict[str, Any]) -> dict[str, Any]:
        cp = dict(cp)
        cp["checkpoint_hash"] = checkpoint_hash(cp)
        atomic_write_json(self.checkpoint_path(cp["mission_id"], cp["token"]), cp)
        return cp

    def _load_and_validate_checkpoint(self, mission_id: str, token: str, supplied: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
        cp = supplied
        if cp is None:
            path = self.checkpoint_path(mission_id, token)
            if not path.exists():
                return None, None
            cp = read_json(path)
        if cp.get("mission_id") != mission_id or cp.get("token") != token:
            return None, "CHECKPOINT_IDENTITY_MISMATCH"
        expected = cp.get("checkpoint_hash")
        if not expected or checkpoint_hash(cp) != expected:
            return None, "CHECKPOINT_HASH_MISMATCH"
        required = {"current_state", "highest_progress_token", "next_action", "completed_steps", "pending_steps", "result_hash", "recoverable"}
        if not required.issubset(cp):
            return None, "CHECKPOINT_SCHEMA_INVALID"
        if not cp.get("recoverable", False):
            return None, "CHECKPOINT_NOT_RECOVERABLE"
        return cp, None

    def run(self, trigger: dict[str, Any], checkpoint: dict[str, Any] | None = None) -> RunResult:
        valid, reason = self.validate_trigger(trigger)
        if not valid:
            return RunResult(reason, "WAIT_TRIGGER", "READY", None, None, [reason], [])

        mission_id = trigger["MISSION_ID"]
        token = trigger["TOKEN"]
        key = self.assignment_key(mission_id, token)
        runtime = read_json(self.state_path)
        completed = runtime.setdefault("completed_assignments", {})
        active = runtime.setdefault("active_assignments", {})

        if key in completed:
            record = completed[key]
            return RunResult(
                "DUPLICATE_COMPLETED", "WAIT_TRIGGER", "READY",
                record["highest_progress_token"], record["result_hash"],
                ["DUPLICATE_COMPLETED"], [],
            )

        cp, cp_error = self._load_and_validate_checkpoint(mission_id, token, checkpoint)
        if cp_error:
            return RunResult("BLOCKED", "BLOCKED", "WAIT", None, None, ["CHECKPOINT_REJECTED"], [], cp_error)

        highest = 0
        completed_steps: list[str] = []
        pending_steps = ["ENTER_RUNNING", "ARTIFACT_PLAN_CONFIRMED", "RELAY_PREPARED", "RESET_TO_WAIT_TRIGGER"]
        prior_result_hash: str | None = None
        if cp:
            highest = self.progress_value(cp["highest_progress_token"])
            completed_steps = list(cp["completed_steps"])
            pending_steps = list(cp["pending_steps"])
            prior_result_hash = cp.get("result_hash")
            if highest not in (0, 1, 2, 3, 4):
                return RunResult("BLOCKED", "BLOCKED", "WAIT", None, None, ["CHECKPOINT_REJECTED"], [], "PROGRESS_TOKEN_INVALID")
            if len(completed_steps) != highest:
                return RunResult("BLOCKED", "BLOCKED", "WAIT", None, None, ["CHECKPOINT_REJECTED"], [], "PROGRESS_TOKEN_REGRESSION_OR_STEP_MISMATCH")
            expected_steps = ["ENTER_RUNNING", "ARTIFACT_PLAN_CONFIRMED", "RELAY_PREPARED", "RESET_TO_WAIT_TRIGGER"][:highest]
            if completed_steps != expected_steps:
                return RunResult("BLOCKED", "BLOCKED", "WAIT", None, None, ["CHECKPOINT_REJECTED"], [], "DUPLICATE_OR_OUT_OF_ORDER_STEP")

        events: list[str] = []
        executed: list[str] = []
        state = "WAIT_TRIGGER"
        heartbeat = "READY"

        if highest == 4:
            result_path = self.result_path(mission_id, token)
            if not result_path.exists() or sha256_bytes(result_path.read_bytes()) != prior_result_hash:
                return RunResult("BLOCKED", "BLOCKED", "WAIT", self.progress_token(mission_id, token, 4), prior_result_hash, ["COMPLETED_RESULT_MISSING_OR_HASH_MISMATCH"], [], "RESULT_HASH_MISMATCH")
            completed[key] = {
                "status": "COMPLETED",
                "highest_progress_token": self.progress_token(mission_id, token, 4),
                "result_hash": prior_result_hash,
                "final_state": "WAIT_TRIGGER",
            }
            active.pop(key, None)
            atomic_write_json(self.state_path, runtime)
            return RunResult("DUPLICATE_COMPLETED", "WAIT_TRIGGER", "READY", self.progress_token(mission_id, token, 4), prior_result_hash, ["RECOVERED_COMPLETED"], [])

        all_steps = ["ENTER_RUNNING", "ARTIFACT_PLAN_CONFIRMED", "RELAY_PREPARED", "RESET_TO_WAIT_TRIGGER"]
        for index in range(highest, 4):
            step = all_steps[index]
            if step in completed_steps:
                return RunResult("BLOCKED", "BLOCKED", "WAIT", self.progress_token(mission_id, token, highest), prior_result_hash, events, executed, "DUPLICATE_STEP")
            if step == "ENTER_RUNNING":
                state, heartbeat = "RUNNING", "BUSY"
            elif step == "ARTIFACT_PLAN_CONFIRMED":
                state, heartbeat = "RUNNING", "BUSY"
            elif step == "RELAY_PREPARED":
                state, heartbeat = "RELAY_READY", "WAIT"
            elif step == "RESET_TO_WAIT_TRIGGER":
                state, heartbeat = "WAIT_TRIGGER", "READY"
            completed_steps.append(step)
            executed.append(step)
            events.append(step)
            highest += 1
            pending_steps = all_steps[highest:]
            active[key] = {
                "current_state": state,
                "highest_progress_token": self.progress_token(mission_id, token, highest),
            }
            self._save_checkpoint({
                "mission_id": mission_id,
                "token": token,
                "current_state": state,
                "highest_progress_token": self.progress_token(mission_id, token, highest),
                "next_action": pending_steps[0] if pending_steps else "NONE",
                "completed_steps": completed_steps,
                "pending_steps": pending_steps,
                "result_hash": prior_result_hash,
                "recoverable": True,
            })
            atomic_write_json(self.state_path, runtime)

        payload = {
            "mission_id": mission_id,
            "token": token,
            "status": "COMPLETED",
            "final_state": state,
            "heartbeat": heartbeat,
            "highest_progress_token": self.progress_token(mission_id, token, 4),
            "completed_steps": completed_steps,
        }
        result_path = self.result_path(mission_id, token)
        if result_path.exists():
            existing_hash = sha256_bytes(result_path.read_bytes())
            if prior_result_hash and existing_hash == prior_result_hash:
                result_hash = existing_hash
            else:
                return RunResult("BLOCKED", "BLOCKED", "WAIT", self.progress_token(mission_id, token, 4), prior_result_hash, events, executed, "RESULT_ALREADY_EXISTS")
        else:
            atomic_write_json(result_path, payload, refuse_overwrite=True)
            result_hash = sha256_bytes(result_path.read_bytes())

        completed[key] = {
            "status": "COMPLETED",
            "highest_progress_token": self.progress_token(mission_id, token, 4),
            "result_hash": result_hash,
            "final_state": "WAIT_TRIGGER",
        }
        active.pop(key, None)
        atomic_write_json(self.state_path, runtime)
        self._save_checkpoint({
            "mission_id": mission_id,
            "token": token,
            "current_state": "WAIT_TRIGGER",
            "highest_progress_token": self.progress_token(mission_id, token, 4),
            "next_action": "NONE",
            "completed_steps": all_steps,
            "pending_steps": [],
            "result_hash": result_hash,
            "recoverable": True,
        })
        return RunResult("COMPLETED", "WAIT_TRIGGER", "READY", self.progress_token(mission_id, token, 4), result_hash, events, executed)


def make_trigger(token: str = "BOOTSTRAP-0001") -> dict[str, Any]:
    return {
        "MISSION_ID": "WAKE-0001",
        "TARGET": "WORKER-01",
        "ACTION": "START",
        "TOKEN": token,
        "OBJECTIVE": "Execute Wake Mechanism v0.2 simulation.",
        "SUCCESS_CRITERIA": ["persistent idempotency", "checkpoint recovery"],
        "EVIDENCE_REQUIRED": ["state", "checkpoint", "result hash"],
    }
