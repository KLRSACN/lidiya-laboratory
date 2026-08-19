from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from gearbox_controller import GearboxGuardError, select_gear as select_v1

RISK_LEVELS = {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
SECRETARY_LEVELS = {"UNKNOWN", "GREEN", "YELLOW", "ORANGE", "RED"}
VERIFICATION_STAGES = {"UNVERIFIED", "CANDIDATE", "BUILT_NOT_VERIFIED", "C_VERIFIED"}

# These are system-level learning/progress signals, not model-weight updates or proof of consciousness.
EXPERIENCE_WEIGHTS = {
    "VERIFIED_CAPABILITY": 5,
    "VERIFIED_RECOVERY": 4,
    "ROOT_CAUSE_RETEST_PASS": 3,
    "C_VERIFIED_LESSON": 3,
    "DURABLE_PROGRESS": 1,
    "ADVERSARIAL_DEFECT_FOUND": 1,
    "HEARTBEAT": 0,
    "POLL": 0,
    "RETRY": 0,
    "WAIT": 0,
    "SCHEDULER_WAKE": 0,
    "SELF_REPORTED_SUCCESS": 0,
    "UNVERIFIED_SIMULATION": 0,
}

@dataclass(frozen=True)
class GearboxV2Decision:
    selected_gear: str
    base_selected_gear: str
    mode: str
    reason: str
    pressure_score: float
    experience_candidate_delta: int
    checkpoint_required: bool
    receiver_ack_required: bool
    verification_gate: str
    real_experience_claim_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def strict_bool(value: Any, name: str) -> bool:
    """Canonical fail-closed boolean intake for the candidate v2/v2.1 path."""
    if type(value) is not bool:
        raise GearboxGuardError(f"{name} must be bool")
    return value


def _ratio(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GearboxGuardError(f"{name} must be numeric")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise GearboxGuardError(f"{name} must be in [0,1]")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GearboxGuardError(f"{name} must be a nonnegative integer")
    return value


def experience_candidate_delta(event_kind: str, *, independently_verified: bool = False) -> int:
    independently_verified = strict_bool(independently_verified, "independently_verified")
    kind = str(event_kind).strip().upper()
    if kind not in EXPERIENCE_WEIGHTS:
        return 0
    value = EXPERIENCE_WEIGHTS[kind]
    if kind in {"VERIFIED_CAPABILITY", "VERIFIED_RECOVERY", "ROOT_CAUSE_RETEST_PASS", "C_VERIFIED_LESSON"}:
        return value if independently_verified else 0
    return value


def _gear_number(gear: str) -> int:
    if not gear.startswith("G"):
        return 0
    return int(gear[1:])


def _cap_gear(gear: str, max_gear: int) -> str:
    if not gear.startswith("G"):
        return gear
    return f"G{min(_gear_number(gear), max_gear)}"


def select_gear_v2(
    *,
    risk: str,
    uncertainty: float,
    evidence_quality: float,
    task_complexity: float,
    reversibility: bool,
    storage_pressure_ratio: float = 0.0,
    context_load_ratio: float = 0.0,
    tool_failure_ratio: float = 0.0,
    stale_pointer_ratio: float = 0.0,
    route_drift: bool = False,
    continuity_anchor_health: float = 1.0,
    recovery_active: bool = False,
    secretary_level: str = "UNKNOWN",
    verification_stage: str = "UNVERIFIED",
    current_gear: str = "G1",
    durable_progress_age_ratio: float = 0.0,
    event_kind: str = "WAIT",
    event_independently_verified: bool = False,
    contradiction: bool = False,
    hard_safety_conflict: bool = False,
    rollback_required: bool = False,
    standby: bool = False,
    proposed_autonomy: int = 6,
) -> GearboxV2Decision:
    risk = str(risk).strip().upper()
    secretary_level = str(secretary_level).strip().upper()
    verification_stage = str(verification_stage).strip().upper()
    current_gear = str(current_gear).strip().upper()
    if risk not in RISK_LEVELS:
        raise GearboxGuardError("invalid risk")
    if secretary_level not in SECRETARY_LEVELS:
        raise GearboxGuardError("invalid secretary_level")
    if verification_stage not in VERIFICATION_STAGES:
        raise GearboxGuardError("invalid verification_stage")
    if current_gear not in {"G1", "G2", "G3", "G4", "G5", "G6"}:
        raise GearboxGuardError("current_gear must be G1..G6")

    reversibility = strict_bool(reversibility, "reversibility")
    route_drift = strict_bool(route_drift, "route_drift")
    recovery_active = strict_bool(recovery_active, "recovery_active")
    event_independently_verified = strict_bool(event_independently_verified, "event_independently_verified")
    contradiction = strict_bool(contradiction, "contradiction")
    hard_safety_conflict = strict_bool(hard_safety_conflict, "hard_safety_conflict")
    rollback_required = strict_bool(rollback_required, "rollback_required")
    standby = strict_bool(standby, "standby")

    context = _ratio(context_load_ratio, "context_load_ratio")
    tool_fail = _ratio(tool_failure_ratio, "tool_failure_ratio")
    stale = _ratio(stale_pointer_ratio, "stale_pointer_ratio")
    anchor = _ratio(continuity_anchor_health, "continuity_anchor_health")
    progress_age = _ratio(durable_progress_age_ratio, "durable_progress_age_ratio")
    storage = _ratio(storage_pressure_ratio, "storage_pressure_ratio")
    uncertainty = _ratio(uncertainty, "uncertainty")
    evidence_quality = _ratio(evidence_quality, "evidence_quality")
    task_complexity = _ratio(task_complexity, "task_complexity")
    _nonnegative_int(proposed_autonomy, "proposed_autonomy")
    if proposed_autonomy > 6:
        raise GearboxGuardError("proposed_autonomy must be 0..6")

    base = select_v1(
        risk=risk,
        uncertainty=uncertainty,
        evidence_quality=evidence_quality,
        task_complexity=task_complexity,
        reversibility=reversibility,
        contradiction=contradiction,
        hard_safety_conflict=hard_safety_conflict,
        rollback_required=rollback_required,
        standby=standby,
        storage_pressure_ratio=storage,
        proposed_autonomy=proposed_autonomy,
    )

    pressure = round(min(1.0,
        0.30 * context +
        0.20 * tool_fail +
        0.15 * stale +
        0.15 * storage +
        0.10 * progress_age +
        0.10 * (1.0 - anchor)
    ), 4)

    selected = base.selected_gear
    reasons: list[str] = [base.reason]
    checkpoint = False
    mode = "NORMAL"

    if recovery_active or anchor < 0.50 or secretary_level == "RED":
        selected = "G1"
        mode = "RECOVERY_BRAKE"
        checkpoint = True
        reasons.append("continuity recovery brake")
    elif route_drift or secretary_level == "ORANGE" or pressure >= 0.70:
        selected = _cap_gear(selected, 2)
        mode = "PRESSURE_DOWNSHIFT"
        checkpoint = True
        reasons.append("route/pressure preemption")
    elif secretary_level == "YELLOW" or pressure >= 0.45:
        selected = _cap_gear(selected, 3)
        mode = "CHECKPOINT_DENSE"
        checkpoint = True
        reasons.append("moderate pressure checkpoint density")

    if progress_age >= 0.75:
        selected = _cap_gear(selected, 3)
        checkpoint = True
        reasons.append("durable progress stale")

    if verification_stage in {"UNVERIFIED", "CANDIDATE"} and _gear_number(selected) > 4:
        selected = "G4"
        reasons.append("unverified work capped at G4")

    current_n = _gear_number(current_gear)
    selected_n = _gear_number(selected)
    if selected_n > current_n + 1:
        selected = f"G{current_n + 1}"
        reasons.append("one-step upshift hysteresis")

    exp_delta = experience_candidate_delta(event_kind, independently_verified=event_independently_verified)
    verified_event = exp_delta > 0 and event_kind.upper() in {
        "VERIFIED_CAPABILITY", "VERIFIED_RECOVERY", "ROOT_CAUSE_RETEST_PASS", "C_VERIFIED_LESSON"
    }

    gate = "C_VERIFIED" if verification_stage == "C_VERIFIED" else "NOT_PROMOTION_EVIDENCE"
    return GearboxV2Decision(
        selected_gear=selected,
        base_selected_gear=base.selected_gear,
        mode=mode,
        reason="; ".join(reasons),
        pressure_score=pressure,
        experience_candidate_delta=exp_delta,
        checkpoint_required=checkpoint,
        receiver_ack_required=True,
        verification_gate=gate,
        real_experience_claim_allowed=verified_event and verification_stage == "C_VERIFIED",
    )
