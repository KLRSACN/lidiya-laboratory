from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from heartbeat_engine import HeartbeatEngine, ZERO_EXPERIENCE_DELTA

SCHEMA_VERSION = "1.1"
RUNTIME_ID = "LIDIYA-ALWAYS-ON-RUNTIME-V1-CANDIDATE"
WORK_LIFECYCLE_TARGET_SECONDS = 20 * 60
RECOVERY_TARGET_SECONDS = 5 * 60
CHECKPOINT_TARGET_SECONDS = 10 * 60
MAX_SILENT_STEPS_WITH_WORK = 4
SELF_VERIFIERS = {"RUNTIME_SELF", "ALWAYS_ON_RUNTIME", "W01_RUNTIME"}


class RuntimeContinuityError(RuntimeError):
    pass


@dataclass
class RuntimeState:
    schema_version: str = SCHEMA_VERSION
    runtime_id: str = RUNTIME_ID
    writer_generation: int = 0
    started_at: Optional[int] = None
    last_step_at: Optional[int] = None
    last_progress_at: Optional[int] = None
    last_checkpoint_at: Optional[int] = None
    last_interruption_at: Optional[int] = None
    last_interruption_observation_id: Optional[str] = None
    last_interruption_source: Optional[str] = None
    last_recovery_attempt_at: Optional[int] = None
    last_recovery_verified_at: Optional[int] = None
    last_recovery_evidence_ref: Optional[str] = None
    last_recovery_verifier: Optional[str] = None
    work_lifecycle_started_at: Optional[int] = None
    lifecycle_cycles_completed: int = 0
    durable_progress_events: int = 0
    checkpoint_count: int = 0
    interruption_count: int = 0
    recovery_attempt_count: int = 0
    recovery_verified_count: int = 0
    silent_steps_with_work: int = 0
    status: str = "INITIALIZING"
    pending_recovery_reason: Optional[str] = None
    last_outcome: str = "NONE"
    real_5min_runtime_live: bool = False


@dataclass(frozen=True)
class RuntimeStepResult:
    disposition: str
    status: str
    heartbeat_disposition: str
    heartbeat_sequence: int
    durable_progress_events: int
    checkpoint_required: bool
    recovery_required: bool
    recovery_sla_candidate: Optional[bool]
    lifecycle_target_met: bool
    writer_generation: int
    real_5min_runtime_live: bool
    experience_delta: Dict[str, int]


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


class AlwaysOnRuntime:
    """Persistent continuity shell around the verified HeartbeatEngine.

    The class is evidence plumbing, not an always-on process by itself. Formal
    five-minute liveness needs an authorized external runner plus independent
    verification. Interruption timestamps cannot be backfilled through step();
    they must be registered when observed with an observation id/source.
    """

    def __init__(self, state_path: str | Path, heartbeat_state_path: str | Path):
        self.state_path = Path(state_path)
        self.heartbeat = HeartbeatEngine(heartbeat_state_path, interval_seconds=300)
        self.state = self._load_or_initialize()

    def _load_or_initialize(self) -> RuntimeState:
        if not self.state_path.exists():
            state = RuntimeState()
            self._persist(state)
            return state
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeContinuityError("unsupported runtime state schema")
        state = RuntimeState(**data)
        if state.real_5min_runtime_live:
            raise RuntimeContinuityError("candidate cannot self-assert real_5min_runtime_live")
        if state.writer_generation < 0:
            raise RuntimeContinuityError("invalid writer_generation")
        return state

    def _persist(self, state: RuntimeState) -> None:
        if state.real_5min_runtime_live:
            raise RuntimeContinuityError("real_5min runtime requires external evidence/formal promotion")
        _atomic_write_json(self.state_path, asdict(state))

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self.state)

    def _cas_guard(self, expected_generation: Optional[int]) -> None:
        if expected_generation is not None and expected_generation != self.state.writer_generation:
            raise RuntimeContinuityError(
                f"stale runtime writer generation expected={expected_generation} actual={self.state.writer_generation}"
            )

    def observe_interruption(
        self,
        *,
        now: int,
        observation_id: str,
        source: str,
        expected_generation: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Register an interruption at observation time; no caller-supplied past timestamp exists."""
        self._cas_guard(expected_generation)
        now = int(now)
        oid = str(observation_id).strip()
        src = str(source).strip()
        if not oid or not src:
            raise RuntimeContinuityError("observation_id and source required")
        if src.upper() in SELF_VERIFIERS:
            raise RuntimeContinuityError("runtime self-observation cannot serve as external SLA evidence")
        if self.state.last_step_at is not None and now < self.state.last_step_at:
            raise RuntimeContinuityError("interruption observation clock rollback detected")
        if self.state.last_interruption_observation_id == oid:
            return {
                "disposition": "DUPLICATE_INTERRUPTION_OBSERVATION_NO_OP",
                "changed": False,
                "real_5min_runtime_live": False,
                "experience_delta": dict(ZERO_EXPERIENCE_DELTA),
            }
        self.state.last_interruption_at = now
        self.state.last_interruption_observation_id = oid
        self.state.last_interruption_source = src
        self.state.interruption_count += 1
        self.state.pending_recovery_reason = "INTERRUPTION_OBSERVED"
        self.state.status = "RECOVERY_REQUIRED"
        self.state.writer_generation += 1
        self.state.last_outcome = "INTERRUPTION_OBSERVED"
        self._persist(self.state)
        return {
            "disposition": "INTERRUPTION_OBSERVED",
            "changed": True,
            "observed_at": now,
            "observation_id": oid,
            "source": src,
            "real_5min_runtime_live": False,
            "experience_delta": dict(ZERO_EXPERIENCE_DELTA),
        }

    def step(
        self,
        *,
        now: int,
        work_pending: bool,
        durable_progress: bool = False,
        durable_checkpoint_ok: bool = False,
        endpoint_ok: bool = True,
        expected_generation: Optional[int] = None,
    ) -> RuntimeStepResult:
        self._cas_guard(expected_generation)
        now = int(now)
        if self.state.last_step_at is not None and now < self.state.last_step_at:
            raise RuntimeContinuityError("runtime clock rollback detected")
        if self.state.started_at is None:
            self.state.started_at = now
        if self.state.work_lifecycle_started_at is None and work_pending:
            self.state.work_lifecycle_started_at = now

        heartbeat = self.heartbeat.tick(now=now, endpoint_ok=endpoint_ok)
        self.state.last_step_at = now
        if heartbeat.endpoint_status == "STALE":
            self.state.pending_recovery_reason = self.state.pending_recovery_reason or "HEARTBEAT_ENDPOINT_STALE"

        if durable_progress:
            self.state.last_progress_at = now
            self.state.durable_progress_events += 1
            self.state.silent_steps_with_work = 0
        elif work_pending:
            self.state.silent_steps_with_work += 1
        else:
            self.state.silent_steps_with_work = 0

        checkpoint_required = False
        if durable_checkpoint_ok:
            self.state.last_checkpoint_at = now
            self.state.checkpoint_count += 1
        elif work_pending:
            anchor = self.state.last_checkpoint_at
            if anchor is None:
                anchor = self.state.work_lifecycle_started_at
            if anchor is not None and now - anchor >= CHECKPOINT_TARGET_SECONDS:
                checkpoint_required = True

        progress_anchor = self.state.last_progress_at or self.state.work_lifecycle_started_at
        if work_pending and progress_anchor is not None:
            if now - progress_anchor >= WORK_LIFECYCLE_TARGET_SECONDS:
                self.state.pending_recovery_reason = "WORK_PROGRESS_STALLED_20M"
        if work_pending and self.state.silent_steps_with_work >= MAX_SILENT_STEPS_WITH_WORK:
            self.state.pending_recovery_reason = self.state.pending_recovery_reason or "SILENT_WORK_STEPS"

        lifecycle_target_met = False
        if work_pending and self.state.work_lifecycle_started_at is not None:
            lifecycle_target_met = now - self.state.work_lifecycle_started_at >= WORK_LIFECYCLE_TARGET_SECONDS
        elif not work_pending and self.state.work_lifecycle_started_at is not None:
            elapsed = now - self.state.work_lifecycle_started_at
            if elapsed >= WORK_LIFECYCLE_TARGET_SECONDS:
                self.state.lifecycle_cycles_completed += 1
                lifecycle_target_met = True
            self.state.work_lifecycle_started_at = None

        recovery_required = self.state.pending_recovery_reason is not None
        recovery_sla_candidate: Optional[bool] = None
        if recovery_required:
            self.state.status = "RECOVERY_REQUIRED"
            if self.state.last_interruption_at is not None:
                recovery_sla_candidate = 0 <= now - self.state.last_interruption_at <= RECOVERY_TARGET_SECONDS
        elif work_pending:
            self.state.status = "ACTIVE"
        else:
            self.state.status = "IDLE_HEALTHY"

        self.state.writer_generation += 1
        self.state.last_outcome = "STEP_RECORDED"
        self._persist(self.state)
        return RuntimeStepResult(
            "STEP_RECORDED", self.state.status, heartbeat.disposition,
            heartbeat.pulse_sequence, self.state.durable_progress_events,
            checkpoint_required, recovery_required, recovery_sla_candidate,
            lifecycle_target_met, self.state.writer_generation, False,
            dict(ZERO_EXPERIENCE_DELTA),
        )

    def prepare_recovery(self, *, now: int, expected_generation: Optional[int] = None) -> Dict[str, Any]:
        self._cas_guard(expected_generation)
        now = int(now)
        if self.state.pending_recovery_reason is None:
            return {"disposition": "RECOVERY_NOT_REQUIRED", "changed": False,
                    "real_5min_runtime_live": False, "experience_delta": dict(ZERO_EXPERIENCE_DELTA)}
        self.state.last_recovery_attempt_at = now
        self.state.recovery_attempt_count += 1
        self.state.status = "RECOVERY_PREPARED"
        self.state.writer_generation += 1
        self.state.last_outcome = "RECOVERY_PREPARED"
        self._persist(self.state)
        latency = None if self.state.last_interruption_at is None else now - self.state.last_interruption_at
        return {
            "disposition": "RECOVERY_PREPARED", "changed": True,
            "reason": self.state.pending_recovery_reason,
            "recovery_latency_seconds": latency,
            "within_5min_target": latency is not None and 0 <= latency <= RECOVERY_TARGET_SECONDS,
            "real_5min_runtime_live": False,
            "experience_delta": dict(ZERO_EXPERIENCE_DELTA),
        }

    def mark_recovery_verified(
        self,
        *,
        now: int,
        recovery_id: str,
        verification_evidence_ref: str,
        verified_by: str,
        expected_generation: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Close recovery only with an explicit non-self verifier/evidence reference."""
        self._cas_guard(expected_generation)
        evidence = str(verification_evidence_ref).strip()
        verifier = str(verified_by).strip()
        if not evidence or not verifier:
            raise RuntimeContinuityError("verification_evidence_ref and verified_by required")
        if verifier.upper() in SELF_VERIFIERS:
            raise RuntimeContinuityError("runtime cannot verify its own recovery")
        if self.state.pending_recovery_reason is None:
            return {"disposition": "RECOVERY_NOT_REQUIRED", "changed": False,
                    "real_5min_runtime_live": False, "experience_delta": dict(ZERO_EXPERIENCE_DELTA)}
        if self.state.last_recovery_attempt_at is None:
            raise RuntimeContinuityError("verified recovery requires a prior recovery attempt")
        heartbeat_recovery = self.heartbeat.mark_verified_recovery(recovery_id=recovery_id)
        self.state.last_recovery_verified_at = int(now)
        self.state.last_recovery_evidence_ref = evidence
        self.state.last_recovery_verifier = verifier
        self.state.recovery_verified_count += 1
        self.state.pending_recovery_reason = None
        self.state.silent_steps_with_work = 0
        self.state.status = "ACTIVE" if self.state.work_lifecycle_started_at is not None else "IDLE_HEALTHY"
        self.state.writer_generation += 1
        self.state.last_outcome = "RECOVERY_VERIFIED"
        self._persist(self.state)
        latency = None if self.state.last_interruption_at is None else int(now) - self.state.last_interruption_at
        return {
            "disposition": "RECOVERY_VERIFIED", "changed": True,
            "verified_by": verifier, "verification_evidence_ref": evidence,
            "heartbeat_recovery": heartbeat_recovery,
            "recovery_latency_seconds": latency,
            "within_5min_target": latency is not None and 0 <= latency <= RECOVERY_TARGET_SECONDS,
            "real_5min_runtime_live": False,
            "experience_delta": dict(ZERO_EXPERIENCE_DELTA),
        }

    def compact_evidence(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "runtime_id": RUNTIME_ID,
            "status": self.state.status,
            "writer_generation": self.state.writer_generation,
            "last_step_at": self.state.last_step_at,
            "last_progress_at": self.state.last_progress_at,
            "last_checkpoint_at": self.state.last_checkpoint_at,
            "last_interruption_at": self.state.last_interruption_at,
            "last_interruption_observation_id": self.state.last_interruption_observation_id,
            "last_interruption_source": self.state.last_interruption_source,
            "last_recovery_attempt_at": self.state.last_recovery_attempt_at,
            "last_recovery_verified_at": self.state.last_recovery_verified_at,
            "last_recovery_evidence_ref": self.state.last_recovery_evidence_ref,
            "last_recovery_verifier": self.state.last_recovery_verifier,
            "lifecycle_cycles_completed": self.state.lifecycle_cycles_completed,
            "durable_progress_events": self.state.durable_progress_events,
            "checkpoint_count": self.state.checkpoint_count,
            "interruption_count": self.state.interruption_count,
            "recovery_attempt_count": self.state.recovery_attempt_count,
            "recovery_verified_count": self.state.recovery_verified_count,
            "pending_recovery_reason": self.state.pending_recovery_reason,
            "heartbeat": self.heartbeat.compact_record(),
            "real_5min_runtime_live": False,
            "experience_delta": dict(ZERO_EXPERIENCE_DELTA),
        }
