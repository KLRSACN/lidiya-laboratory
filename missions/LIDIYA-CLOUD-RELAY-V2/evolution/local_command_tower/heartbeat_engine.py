from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional

MIN_INTERVAL_SECONDS = 300
MAX_INTERVAL_SECONDS = 600
COMPACT_CADENCE_PULSES = 12
STALE_AFTER_MISSES = 2
MAX_RECENT_PULSE_IDS = 512
STATE_SCHEMA_VERSION = "1.0"


class HeartbeatError(RuntimeError):
    pass


class StaleWriterError(HeartbeatError):
    pass


class InvalidHeartbeatConfig(HeartbeatError):
    pass


@dataclass
class HeartbeatState:
    schema_version: str = STATE_SCHEMA_VERSION
    interval_seconds: int = MIN_INTERVAL_SECONDS
    pulse_sequence: int = 0
    event_cursor: int = 0
    last_pulse_at: Optional[int] = None
    next_due_at: Optional[int] = None
    writer_generation: int = 0
    endpoint_status: str = "UNKNOWN"
    consecutive_misses: int = 0
    last_recovery_id: Optional[str] = None
    recent_pulse_ids: list[str] = field(default_factory=list)
    compact_records: int = 0


@dataclass(frozen=True)
class PulseResult:
    disposition: str
    pulse_id: str
    executed: bool
    pulse_sequence: int
    event_cursor: int
    endpoint_status: str
    compact_required: bool
    writer_generation: int
    experience_delta: Dict[str, int]


ZERO_EXPERIENCE_DELTA = {
    "recurrence": 0,
    "emotion": 0,
    "self_identity_relevance": 0,
    "verified_count": 0,
    "p_base_evidence": 0,
}


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _validate_interval(interval_seconds: int) -> None:
    if not MIN_INTERVAL_SECONDS <= int(interval_seconds) <= MAX_INTERVAL_SECONDS:
        raise InvalidHeartbeatConfig(
            f"interval_seconds must be within {MIN_INTERVAL_SECONDS}..{MAX_INTERVAL_SECONDS}"
        )


def canonical_pulse_id(sequence: int, scheduled_at: int) -> str:
    raw = f"heartbeat:{int(sequence)}:{int(scheduled_at)}".encode("utf-8")
    return "hb-" + hashlib.sha256(raw).hexdigest()[:24]


def validate_experience_event(event: Dict[str, Any], *, pulse_id: Optional[str] = None) -> None:
    source_event_id = str(event.get("source_event_id", "")).strip()
    provenance = str(event.get("provenance", "")).strip()
    if not source_event_id or not provenance:
        raise HeartbeatError("Experience requires distinct source_event_id and provenance")
    if pulse_id is not None and source_event_id == pulse_id:
        raise HeartbeatError("pulse_id must never be used as Experience source_event_id")


class HeartbeatEngine:
    """Deterministic bounded heartbeat state machine.

    Heartbeat state is a control/liveness domain. It never opens or mutates formal
    MISSION_STATE, packet state, dialogue state, or personality/memory evidence.
    """

    def __init__(self, state_path: str | Path, *, interval_seconds: int = MIN_INTERVAL_SECONDS):
        _validate_interval(interval_seconds)
        self.state_path = Path(state_path)
        self._requested_interval = int(interval_seconds)
        self.state = self._load_or_initialize()

    def _load_or_initialize(self) -> HeartbeatState:
        if not self.state_path.exists():
            state = HeartbeatState(interval_seconds=self._requested_interval)
            self._persist(state)
            return state
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != STATE_SCHEMA_VERSION:
            raise HeartbeatError("unsupported heartbeat state schema")
        _validate_interval(int(data.get("interval_seconds", 0)))
        state = HeartbeatState(**data)
        if state.event_cursor < state.pulse_sequence:
            raise HeartbeatError("event_cursor rollback detected")
        if state.writer_generation < 0:
            raise HeartbeatError("invalid writer_generation")
        return state

    def _persist(self, state: HeartbeatState) -> None:
        _atomic_write_json(self.state_path, asdict(state))

    def _cas_guard(self, expected_generation: Optional[int]) -> None:
        if expected_generation is not None and expected_generation != self.state.writer_generation:
            raise StaleWriterError(
                f"stale writer generation: expected={expected_generation} actual={self.state.writer_generation}"
            )

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self.state)

    def due(self, now: int) -> bool:
        return self.state.next_due_at is None or int(now) >= self.state.next_due_at

    def tick(
        self,
        *,
        now: int,
        pulse_id: Optional[str] = None,
        expected_generation: Optional[int] = None,
        endpoint_ok: bool = True,
    ) -> PulseResult:
        self._cas_guard(expected_generation)
        now = int(now)
        if not self.due(now):
            return PulseResult(
                disposition="NOT_DUE",
                pulse_id=pulse_id or "",
                executed=False,
                pulse_sequence=self.state.pulse_sequence,
                event_cursor=self.state.event_cursor,
                endpoint_status=self.state.endpoint_status,
                compact_required=False,
                writer_generation=self.state.writer_generation,
                experience_delta=dict(ZERO_EXPERIENCE_DELTA),
            )

        scheduled_at = self.state.next_due_at if self.state.next_due_at is not None else now
        proposed_seq = self.state.pulse_sequence + 1
        pid = pulse_id or canonical_pulse_id(proposed_seq, scheduled_at)
        if pid in self.state.recent_pulse_ids:
            return PulseResult(
                disposition="DUPLICATE_NO_OP",
                pulse_id=pid,
                executed=False,
                pulse_sequence=self.state.pulse_sequence,
                event_cursor=self.state.event_cursor,
                endpoint_status=self.state.endpoint_status,
                compact_required=False,
                writer_generation=self.state.writer_generation,
                experience_delta=dict(ZERO_EXPERIENCE_DELTA),
            )

        self.state.pulse_sequence += 1
        self.state.event_cursor += 1
        self.state.last_pulse_at = now
        self.state.next_due_at = now + self.state.interval_seconds
        self.state.writer_generation += 1
        self.state.recent_pulse_ids.append(pid)
        if len(self.state.recent_pulse_ids) > MAX_RECENT_PULSE_IDS:
            self.state.recent_pulse_ids = self.state.recent_pulse_ids[-MAX_RECENT_PULSE_IDS:]

        material_anomaly = False
        if endpoint_ok:
            self.state.consecutive_misses = 0
            if self.state.endpoint_status in {"UNKNOWN", "HEALTHY"}:
                self.state.endpoint_status = "HEALTHY"
        else:
            self.state.consecutive_misses += 1
            if self.state.consecutive_misses >= STALE_AFTER_MISSES:
                if self.state.endpoint_status != "STALE":
                    material_anomaly = True
                self.state.endpoint_status = "STALE"

        cadence_compact = self.state.pulse_sequence % COMPACT_CADENCE_PULSES == 0
        compact_required = cadence_compact or material_anomaly
        if compact_required:
            self.state.compact_records += 1
        self._persist(self.state)

        return PulseResult(
            disposition="EXECUTED",
            pulse_id=pid,
            executed=True,
            pulse_sequence=self.state.pulse_sequence,
            event_cursor=self.state.event_cursor,
            endpoint_status=self.state.endpoint_status,
            compact_required=compact_required,
            writer_generation=self.state.writer_generation,
            experience_delta=dict(ZERO_EXPERIENCE_DELTA),
        )

    def mark_verified_recovery(
        self,
        *,
        recovery_id: str,
        expected_generation: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._cas_guard(expected_generation)
        rid = recovery_id.strip()
        if not rid:
            raise HeartbeatError("recovery_id required")
        if self.state.last_recovery_id == rid:
            return {
                "disposition": "DUPLICATE_RECOVERY_NO_OP",
                "changed": False,
                "endpoint_status": self.state.endpoint_status,
                "writer_generation": self.state.writer_generation,
            }
        if self.state.endpoint_status != "STALE":
            return {
                "disposition": "RECOVERY_NOT_REQUIRED",
                "changed": False,
                "endpoint_status": self.state.endpoint_status,
                "writer_generation": self.state.writer_generation,
            }
        self.state.last_recovery_id = rid
        self.state.endpoint_status = "HEALTHY"
        self.state.consecutive_misses = 0
        self.state.event_cursor += 1
        self.state.writer_generation += 1
        self.state.compact_records += 1
        self._persist(self.state)
        return {
            "disposition": "VERIFIED_RECOVERY_APPLIED",
            "changed": True,
            "endpoint_status": self.state.endpoint_status,
            "writer_generation": self.state.writer_generation,
            "experience_delta": dict(ZERO_EXPERIENCE_DELTA),
        }

    def compact_record(self) -> Dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "pulse_sequence": self.state.pulse_sequence,
            "event_cursor": self.state.event_cursor,
            "last_pulse_at": self.state.last_pulse_at,
            "next_due_at": self.state.next_due_at,
            "endpoint_status": self.state.endpoint_status,
            "consecutive_misses": self.state.consecutive_misses,
            "writer_generation": self.state.writer_generation,
            "compact_records": self.state.compact_records,
            "experience_delta": dict(ZERO_EXPERIENCE_DELTA),
        }
