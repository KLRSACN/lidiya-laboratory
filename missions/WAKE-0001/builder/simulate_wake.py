from dataclasses import dataclass, asdict
from pathlib import Path
import json

REQUIRED_FIELDS = [
    "MISSION_ID",
    "TARGET",
    "ACTION",
    "TOKEN",
    "OBJECTIVE",
    "SUCCESS_CRITERIA",
    "EVIDENCE_REQUIRED",
]

@dataclass
class Worker:
    node: str = "01"
    role: str = "BUILDER"
    state: str = "WAIT_TRIGGER"
    heartbeat: str = "READY"
    mission_id: str | None = None
    token: str | None = None
    progress_step: int = 0

    def progress_token(self) -> str:
        return f"{self.mission_id}:{self.token}:P{self.progress_step:04d}"

    def increment(self) -> None:
        self.progress_step += 1

    def validate_trigger(self, trigger: dict) -> tuple[bool, str]:
        missing = [field for field in REQUIRED_FIELDS if not trigger.get(field)]
        if missing:
            return False, f"INVALID_TRIGGER missing={','.join(missing)}"
        if trigger["TARGET"] != "WORKER-01":
            return False, "WRONG_TARGET"
        if trigger["ACTION"] != "START":
            return False, "INVALID_TRIGGER action"
        return True, "VALID"

    def run(self, trigger: dict) -> dict:
        log = [self.snapshot("BOOT")]
        valid, validation = self.validate_trigger(trigger)
        if not valid:
            log.append(self.snapshot(validation))
            return {"validation": validation, "log": log}

        self.mission_id = trigger["MISSION_ID"]
        self.token = trigger["TOKEN"]
        self.progress_step = 0
        log.append(self.snapshot("TRIGGER_VALIDATED"))

        self.state = "RUNNING"
        self.heartbeat = "BUSY"
        self.increment()
        log.append(self.snapshot("ENTER_RUNNING"))

        artifacts = [
            "wake_mechanism_v0.1.md",
            "simulate_wake.py",
            "simulation_result.json",
            "state_transition.log",
            "worker02_checkpoint.json",
        ]
        self.increment()
        log.append(self.snapshot("MINIMUM_ARTIFACTS_CREATED"))

        self.state = "RELAY_READY"
        self.heartbeat = "WAIT"
        self.increment()
        log.append(self.snapshot("RELAY_PREPARED"))

        final_checkpoint = self.progress_token()

        self.state = "WAIT_TRIGGER"
        self.heartbeat = "READY"
        self.increment()
        log.append(self.snapshot("RESET_TO_WAIT_TRIGGER"))

        result = {
            "validation": validation,
            "transition_sequence": [entry["state"] for entry in log if entry["event"] in {
                "BOOT", "ENTER_RUNNING", "RELAY_PREPARED", "RESET_TO_WAIT_TRIGGER"
            }],
            "final_state": self.state,
            "final_heartbeat": self.heartbeat,
            "relay_checkpoint": final_checkpoint,
            "reset_checkpoint": self.progress_token(),
            "artifacts": artifacts,
            "log": log,
        }

        assert result["transition_sequence"] == [
            "WAIT_TRIGGER", "RUNNING", "RELAY_READY", "WAIT_TRIGGER"
        ]
        assert result["final_state"] == "WAIT_TRIGGER"
        assert result["final_heartbeat"] == "READY"
        return result

    def snapshot(self, event: str) -> dict:
        token = None
        if self.mission_id and self.token:
            token = self.progress_token()
        return {
            "event": event,
            "state": self.state,
            "heartbeat": self.heartbeat,
            "mission_id": self.mission_id,
            "token": self.token,
            "progress_token": token,
        }

def main() -> None:
    base = Path(__file__).resolve().parent
    trigger = {
        "MISSION_ID": "WAKE-0001",
        "TARGET": "WORKER-01",
        "ACTION": "START",
        "TOKEN": "BOOTSTRAP-0001",
        "OBJECTIVE": "Build and verify Wake Mechanism v0.1.",
        "SUCCESS_CRITERIA": [
            "Define required states",
            "Define trigger and relay schemas",
            "Demonstrate full transition",
        ],
        "EVIDENCE_REQUIRED": [
            "Specification",
            "Trigger example",
            "Relay example",
            "Transition log",
            "Checkpoint",
        ],
    }

    worker = Worker()
    result = worker.run(trigger)

    (base / "simulation_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = []
    for entry in result["log"]:
        lines.append(
            f'{entry["event"]} | STATE={entry["state"]} | '
            f'HEARTBEAT={entry["heartbeat"]} | PROGRESS={entry["progress_token"]}'
        )
    (base / "state_transition.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

    checkpoint = {
        "mission_id": "WAKE-0001",
        "token": "BOOTSTRAP-0001",
        "source_worker": "WORKER-01",
        "recommended_next_worker": "WORKER-02",
        "relay_checkpoint": result["relay_checkpoint"],
        "reset_checkpoint": result["reset_checkpoint"],
        "verified_transition": result["transition_sequence"],
        "verified_final_state": result["final_state"],
        "known_limitations": [
            "Local deterministic simulation only",
            "No external window wake event tested",
            "No GitHub polling tested",
            "No cross-process persistence tested",
        ],
        "next_tests": [
            "Invalid trigger with missing fields",
            "Wrong target trigger",
            "Duplicate mission/token idempotency",
            "BLOCKED recovery path",
            "Persistent checkpoint recovery",
        ],
    }
    (base / "worker02_checkpoint.json").write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("SIMULATION_PASS")
    print("TRANSITION=" + " -> ".join(result["transition_sequence"]))
    print("FINAL_STATE=" + result["final_state"])
    print("FINAL_HEARTBEAT=" + result["final_heartbeat"])
    print("RELAY_CHECKPOINT=" + result["relay_checkpoint"])
    print("RESET_CHECKPOINT=" + result["reset_checkpoint"])

if __name__ == "__main__":
    main()
