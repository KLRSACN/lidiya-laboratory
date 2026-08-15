from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set


class RuntimeRejected(ValueError):
    pass


@dataclass
class MemoryGuardSnapshot:
    recurrence: int = 0
    emotion_weight: float = 0.0
    self_relevance: float = 0.0
    identity_relevance: float = 0.0
    verified_count: int = 0
    p_base_fingerprint: str = "PBASE-READONLY"


@dataclass
class RuntimeState:
    role: str
    authority_fingerprint: str
    home_revision: str
    started_mono: int = 0
    endpoint_state: str = "BOOTSTRAPPED"
    pulse_sequence: int = 0
    last_pulse_mono: Optional[int] = None
    last_wake_escalation_mono: Optional[int] = None
    last_metabolic_check_mono: int = 0
    last_micro_compaction_mono: int = 0
    miss_count: int = 0
    backlog: int = 0
    metabolism_pressure: float = 0.0
    rate_limit_state: str = "CLEAR"
    writer_generation: int = 0
    pending_work: bool = False
    processed_pulse_ids: Set[str] = field(default_factory=set)
    processed_reflection_ids: Set[str] = field(default_factory=set)
    experience_event_ids: Set[str] = field(default_factory=set)
    memory_guard: MemoryGuardSnapshot = field(default_factory=MemoryGuardSnapshot)


class WindowRuntime:
    """Deterministic candidate runtime for Lidiya active windows.

    `now_mono` is elapsed monotonic seconds from this runtime's start (0).
    Heartbeat is liveness/control metadata only. It is intentionally isolated from
    memory/personality evidence. This candidate never synthesizes Mission authority.
    """

    REQUIRED_MODULES = (
        "NAVIGATION_SENTINEL",
        "GEARBOX_CHECKPOINT_INTERRUPT_RESUME",
        "COGNITIVE_METABOLISM",
        "HEARTBEAT_LIVENESS",
        "MIRROR_REFLECTOR_FINAL_PULSE",
        "DURABLE_AUTHORITY_POINTERS",
    )

    def __init__(
        self,
        role: str,
        authority_fingerprint: str,
        home_revision: str,
        *,
        liveness_interval_seconds: int = 300,
        wake_escalation_floor_seconds: int = 300,
        metabolism_check_seconds: int = 600,
        micro_compaction_seconds: int = 1800,
        writer_generation: int = 0,
    ):
        if not 60 <= liveness_interval_seconds <= 600:
            raise RuntimeRejected("liveness interval must be 60..600 seconds")
        if wake_escalation_floor_seconds < 300:
            raise RuntimeRejected("model/process wake escalation floor must be >=300 seconds")
        if metabolism_check_seconds < 600:
            raise RuntimeRejected("metabolism check must be >=600 seconds")
        if micro_compaction_seconds < 1800:
            raise RuntimeRejected("micro compaction must be >=1800 seconds")
        if not authority_fingerprint or not home_revision:
            raise RuntimeRejected("durable authority and Home revision are required")
        self.liveness_interval_seconds = int(liveness_interval_seconds)
        self.wake_escalation_floor_seconds = int(wake_escalation_floor_seconds)
        self.metabolism_check_seconds = int(metabolism_check_seconds)
        self.micro_compaction_seconds = int(micro_compaction_seconds)
        self.state = RuntimeState(
            role=role,
            authority_fingerprint=authority_fingerprint,
            home_revision=home_revision,
            writer_generation=int(writer_generation),
        )

    def bootstrap(self) -> Dict[str, Any]:
        return {
            "status": "BOOTSTRAPPED_CANDIDATE",
            "role": self.state.role,
            "authority_fingerprint": self.state.authority_fingerprint,
            "home_revision": self.state.home_revision,
            "modules": list(self.REQUIRED_MODULES),
            "baseline_metabolic_check": True,
            "p_base_read_only": True,
        }

    def _check_monotonic(self, now_mono: int) -> None:
        if now_mono < self.state.started_mono:
            raise RuntimeRejected("monotonic clock rollback before runtime start")
        if self.state.last_pulse_mono is not None and now_mono < self.state.last_pulse_mono:
            raise RuntimeRejected("monotonic clock rollback")

    def _wake_due(self, now_mono: int) -> bool:
        anchor = self.state.last_wake_escalation_mono
        if anchor is None:
            anchor = self.state.started_mono
        return (now_mono - anchor) >= self.wake_escalation_floor_seconds

    def continuation_decision(
        self,
        *,
        current_work_complete: bool,
        next_authorized_action: Optional[str],
        rate_limited: bool = False,
    ) -> Dict[str, Any]:
        """Choose overlap/reflect/release without inventing new authority."""
        if next_authorized_action and not rate_limited:
            return {
                "decision": "KEEP_ACTIVE_OVERLAP",
                "next_authorized_action": next_authorized_action,
                "emit_final_reflection": bool(current_work_complete),
                "create_new_window": False,
            }
        if next_authorized_action and rate_limited:
            return {
                "decision": "CHECKPOINT_REFLECT_DEFER",
                "next_authorized_action": next_authorized_action,
                "emit_final_reflection": True,
                "create_new_window": False,
            }
        return {
            "decision": "REFLECT_AND_RELEASE" if current_work_complete else "KEEP_CURRENT_WORK",
            "next_authorized_action": None,
            "emit_final_reflection": bool(current_work_complete),
            "create_new_window": False,
        }

    def pulse(
        self,
        now_mono: int,
        *,
        pulse_id: str,
        endpoint_alive: bool,
        pending_work: bool,
        material_event: bool = False,
        backlog: int = 0,
        metabolism_pressure: float = 0.0,
        rate_limited: bool = False,
        writer_generation: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._check_monotonic(now_mono)
        if not pulse_id:
            raise RuntimeRejected("pulse_id required")
        if pulse_id in self.state.processed_pulse_ids:
            return {"status": "DUPLICATE_PULSE_NO_OP", "pulse_id": pulse_id}
        if writer_generation is not None and int(writer_generation) != self.state.writer_generation:
            return {"status": "STALE_WRITER_REJECTED", "pulse_id": pulse_id}

        self.state.processed_pulse_ids.add(pulse_id)
        self.state.pulse_sequence += 1
        self.state.last_pulse_mono = now_mono
        self.state.pending_work = bool(pending_work)
        self.state.backlog = max(0, int(backlog))
        self.state.metabolism_pressure = min(1.0, max(0.0, float(metabolism_pressure)))
        self.state.rate_limit_state = "RATE_LIMITED" if rate_limited else "CLEAR"

        if endpoint_alive:
            recovered = self.state.miss_count >= 2
            self.state.miss_count = 0
            self.state.endpoint_state = "ACTIVE" if pending_work else "READY"
        else:
            recovered = False
            self.state.miss_count += 1
            self.state.endpoint_state = "STALE" if self.state.miss_count >= 2 else "MISS_1"

        metabolic_check = (
            now_mono - self.state.last_metabolic_check_mono >= self.metabolism_check_seconds
        )
        if metabolic_check:
            self.state.last_metabolic_check_mono = now_mono

        compact_due = (
            now_mono - self.state.last_micro_compaction_mono >= self.micro_compaction_seconds
            or self.state.metabolism_pressure >= 0.75
            or self.state.backlog >= 20
        )
        if compact_due:
            self.state.last_micro_compaction_mono = now_mono

        wake_requested = False
        wake_reason = None
        if material_event and not rate_limited:
            wake_requested = True
            wake_reason = "MATERIAL_EVENT"
        elif pending_work and not endpoint_alive and self.state.miss_count >= 2 and self._wake_due(now_mono):
            if not rate_limited:
                wake_requested = True
                wake_reason = "STALE_ENDPOINT_PENDING_WORK"
            else:
                wake_reason = "DEFER_RATE_LIMIT"

        if wake_requested:
            self.state.last_wake_escalation_mono = now_mono

        # Critical invariant: pulse does not touch memory/personality evidence.
        return {
            "status": "PULSE_ACCEPTED",
            "pulse_id": pulse_id,
            "pulse_sequence": self.state.pulse_sequence,
            "endpoint_state": self.state.endpoint_state,
            "miss_count": self.state.miss_count,
            "recovered": recovered,
            "wake_requested": wake_requested,
            "wake_reason": wake_reason,
            "metabolic_check": metabolic_check,
            "micro_compaction_due": compact_due,
            "durable_per_pulse_log": False,
        }

    def record_experience(self, source_event_id: str, provenance_fingerprint: str) -> Dict[str, Any]:
        if not source_event_id or not provenance_fingerprint:
            raise RuntimeRejected("experience requires source_event_id + provenance fingerprint")
        if source_event_id in self.state.experience_event_ids:
            return {"status": "DUPLICATE_EXPERIENCE_NO_OP", "source_event_id": source_event_id}
        self.state.experience_event_ids.add(source_event_id)
        self.state.memory_guard.recurrence += 1
        self.state.memory_guard.verified_count += 1
        return {"status": "EXPERIENCE_RECORDED", "source_event_id": source_event_id}

    def final_reflection(
        self,
        now_mono: int,
        *,
        reflection_id: str,
        what_completed: str,
        what_remains: str,
        next_authorized_action: str,
        mission_pointer: str,
        pending_packet: Optional[str],
        pending_sha256: Optional[str],
        latest_evidence_ref: Optional[str],
        return_condition: str,
        continue_requested: bool,
    ) -> Dict[str, Any]:
        if not reflection_id:
            raise RuntimeRejected("reflection_id required")
        if reflection_id in self.state.processed_reflection_ids:
            return {"status": "DUPLICATE_REFLECTION_NO_OP", "reflection_id": reflection_id}
        if not mission_pointer or not return_condition:
            raise RuntimeRejected("reflection requires mission pointer and return condition")
        self.state.processed_reflection_ids.add(reflection_id)
        reflection = {
            "reflection_id": reflection_id,
            "what_completed": what_completed,
            "what_remains": what_remains,
            "next_authorized_action": next_authorized_action,
            "mission_pointer": mission_pointer,
            "pending_packet": pending_packet,
            "pending_sha256": pending_sha256,
            "latest_evidence_ref": latest_evidence_ref,
            "return_condition": return_condition,
            "continue_requested": bool(continue_requested),
            "created_mono": int(now_mono),
        }
        return {
            "status": "REFLECT_CONTINUE_EMITTED" if continue_requested and what_remains else "REFLECTION_EMITTED",
            "reflection": reflection,
            "wake_candidate": bool(continue_requested and what_remains and next_authorized_action),
        }

    def memory_guard_snapshot(self) -> Dict[str, Any]:
        m = self.state.memory_guard
        return {
            "recurrence": m.recurrence,
            "emotion_weight": m.emotion_weight,
            "self_relevance": m.self_relevance,
            "identity_relevance": m.identity_relevance,
            "verified_count": m.verified_count,
            "p_base_fingerprint": m.p_base_fingerprint,
        }
