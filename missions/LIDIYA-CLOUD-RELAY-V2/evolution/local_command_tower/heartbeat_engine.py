from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

MIN_INTERVAL_SECONDS = 300
MAX_INTERVAL_SECONDS = 600
COMPACT_CADENCE_PULSES = 12
STALE_AFTER_MISSES = 2
PULSE_FILTER_BITS = 16384
PULSE_FILTER_HEX_LEN = PULSE_FILTER_BITS // 4
STATE_SCHEMA_VERSION = "1.2"
CANONICAL_ID_RE = re.compile(r"^hb2-([1-9][0-9]*)-([0-9]+)-([0-9a-f]{16})$")

class HeartbeatError(RuntimeError): pass
class StaleWriterError(HeartbeatError): pass
class InvalidHeartbeatConfig(HeartbeatError): pass

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
    pulse_filter_hex: str = "0" * PULSE_FILTER_HEX_LEN
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

def _validate_interval(v: int) -> None:
    if not MIN_INTERVAL_SECONDS <= int(v) <= MAX_INTERVAL_SECONDS:
        raise InvalidHeartbeatConfig(
            f"interval_seconds must be within {MIN_INTERVAL_SECONDS}..{MAX_INTERVAL_SECONDS}"
        )

def _canonical_digest(sequence: int, scheduled_at: int) -> str:
    return hashlib.sha256(
        f"heartbeat:{int(sequence)}:{int(scheduled_at)}".encode()
    ).hexdigest()[:16]

def canonical_pulse_id(sequence: int, scheduled_at: int) -> str:
    sequence = int(sequence)
    scheduled_at = int(scheduled_at)
    if sequence <= 0 or scheduled_at < 0:
        raise HeartbeatError("canonical pulse identity requires positive sequence and nonnegative scheduled_at")
    return f"hb2-{sequence}-{scheduled_at}-{_canonical_digest(sequence, scheduled_at)}"

def parse_canonical_pulse_id(pulse_id: str) -> tuple[int, int]:
    pid = str(pulse_id)
    match = CANONICAL_ID_RE.fullmatch(pid)
    if not match:
        raise HeartbeatError("invalid structured canonical pulse id")
    sequence = int(match.group(1))
    scheduled_at = int(match.group(2))
    digest = match.group(3)
    if sequence <= 0 or scheduled_at < 0:
        raise HeartbeatError("invalid canonical sequence or scheduled_at")
    if digest != _canonical_digest(sequence, scheduled_at):
        raise HeartbeatError("canonical pulse digest mismatch")
    return sequence, scheduled_at

def validate_experience_event(event: Dict[str, Any], *, pulse_id: Optional[str] = None) -> None:
    sid = str(event.get("source_event_id", "")).strip()
    prov = str(event.get("provenance", "")).strip()
    if not sid or not prov:
        raise HeartbeatError("Experience requires distinct source_event_id and provenance")
    if pulse_id is not None and sid == pulse_id:
        raise HeartbeatError("pulse_id must never be used as Experience source_event_id")

class HeartbeatEngine:
    """Deterministic bounded heartbeat state machine.

    Formal exactly-once semantics apply only to STRUCTURED_CANONICAL_PULSE_ID_ONLY.
    Automatic pulses generate the expected structured ID from persisted sequence
    and due time. Caller-supplied opaque IDs are invalid and non-authoritative.
    The legacy bounded pulse_filter_hex field remains only for state compatibility;
    it is never consulted as formal replay/exactness truth.
    """

    def __init__(self, state_path: str | Path, *, interval_seconds: int = MIN_INTERVAL_SECONDS):
        _validate_interval(interval_seconds)
        self.state_path = Path(state_path)
        self._requested_interval = int(interval_seconds)
        self.state = self._load_or_initialize()

    def _load_or_initialize(self) -> HeartbeatState:
        if not self.state_path.exists():
            s = HeartbeatState(interval_seconds=self._requested_interval)
            self._persist(s)
            return s
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != STATE_SCHEMA_VERSION:
            raise HeartbeatError("unsupported heartbeat state schema")
        _validate_interval(int(data.get("interval_seconds", 0)))
        s = HeartbeatState(**data)
        if len(s.pulse_filter_hex) != PULSE_FILTER_HEX_LEN:
            raise HeartbeatError("invalid legacy pulse filter length")
        try:
            int(s.pulse_filter_hex, 16)
        except ValueError as exc:
            raise HeartbeatError("invalid legacy pulse filter encoding") from exc
        if s.event_cursor < s.pulse_sequence:
            raise HeartbeatError("event_cursor rollback detected")
        if s.writer_generation < 0:
            raise HeartbeatError("invalid writer_generation")
        return s

    def _persist(self, s: HeartbeatState) -> None:
        _atomic_write_json(self.state_path, asdict(s))

    def _cas_guard(self, generation: Optional[int]) -> None:
        if generation is not None and generation != self.state.writer_generation:
            raise StaleWriterError(
                f"stale writer generation: expected={generation} actual={self.state.writer_generation}"
            )

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self.state)

    def due(self, now: int) -> bool:
        return self.state.next_due_at is None or int(now) >= self.state.next_due_at

    def _noop(self, disposition: str, pid: str) -> PulseResult:
        return PulseResult(
            disposition, pid, False, self.state.pulse_sequence, self.state.event_cursor,
            self.state.endpoint_status, False, self.state.writer_generation,
            dict(ZERO_EXPERIENCE_DELTA)
        )

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
        expected_sequence = self.state.pulse_sequence + 1
        expected_scheduled_at = self.state.next_due_at if self.state.next_due_at is not None else now

        if pulse_id is None:
            pid = canonical_pulse_id(expected_sequence, expected_scheduled_at)
        else:
            pid = str(pulse_id)
            try:
                sequence, scheduled_at = parse_canonical_pulse_id(pid)
            except HeartbeatError:
                return self._noop("INVALID_EXTERNAL_PULSE_ID_NO_OP", pid)

            if sequence <= self.state.pulse_sequence:
                return self._noop("DUPLICATE_NO_OP", pid)
            if sequence > expected_sequence:
                return self._noop("OUT_OF_ORDER_NO_OP", pid)
            if scheduled_at != expected_scheduled_at:
                return self._noop("INVALID_CANONICAL_ID_NO_OP", pid)

        if not self.due(now):
            return self._noop("NOT_DUE", pid)

        self.state.pulse_sequence += 1
        self.state.event_cursor += 1
        self.state.last_pulse_at = now
        self.state.next_due_at = now + self.state.interval_seconds
        self.state.writer_generation += 1

        anomaly = False
        if endpoint_ok:
            self.state.consecutive_misses = 0
            if self.state.endpoint_status in {"UNKNOWN", "HEALTHY"}:
                self.state.endpoint_status = "HEALTHY"
        else:
            self.state.consecutive_misses += 1
            if self.state.consecutive_misses >= STALE_AFTER_MISSES:
                if self.state.endpoint_status != "STALE":
                    anomaly = True
                self.state.endpoint_status = "STALE"

        compact = self.state.pulse_sequence % COMPACT_CADENCE_PULSES == 0 or anomaly
        if compact:
            self.state.compact_records += 1
        self._persist(self.state)
        return PulseResult(
            "EXECUTED", pid, True, self.state.pulse_sequence, self.state.event_cursor,
            self.state.endpoint_status, compact, self.state.writer_generation,
            dict(ZERO_EXPERIENCE_DELTA)
        )

    def mark_verified_recovery(
        self, *, recovery_id: str, expected_generation: Optional[int] = None
    ) -> Dict[str, Any]:
        self._cas_guard(expected_generation)
        rid = recovery_id.strip()
        if not rid:
            raise HeartbeatError("recovery_id required")
        if self.state.last_recovery_id == rid:
            return {
                "disposition": "DUPLICATE_RECOVERY_NO_OP", "changed": False,
                "endpoint_status": self.state.endpoint_status,
                "writer_generation": self.state.writer_generation,
            }
        if self.state.endpoint_status != "STALE":
            return {
                "disposition": "RECOVERY_NOT_REQUIRED", "changed": False,
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
            "disposition": "VERIFIED_RECOVERY_APPLIED", "changed": True,
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
