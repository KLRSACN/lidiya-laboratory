from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

FORMAL_SLOTS = ("LCR-A", "LCR-B", "LCR-C")
VALID_GEARS = ("N", "R", "G1", "G2", "G3", "G4", "G5", "G6")
HARD_RISK = {"HIGH", "CRITICAL"}
COST_CLASS = {"N": "ZERO", "R": "ZERO", "G1": "TINY", "G2": "SMALL", "G3": "SMALL", "G4": "SMALL", "G5": "MEDIUM", "G6": "REFERENCE"}
SPECIALIST = {"N": "STANDBY", "R": "ROLLBACK_CONTROLLER", "G1": "DETERMINISTIC_START_BRAKE", "G2": "ROUTER", "G3": "EVIDENCE_METABOLISM", "G4": "ROUTINE_PLANNER", "G5": "INTEGRATOR_2B", "G6": "TEACHER_REFERENCE"}
RPM_CONTROL_FIELDS = ("mission_id", "status", "step_id", "current_role", "pending_packet", "pending_packet_sha256", "lease")
TORQUE_FIELDS = ("mission_id", "step_id", "route", "pending_packet", "pending_packet_sha256", "latest_verified_evidence", "rollback_anchor", "blocker", "priority", "return_condition")

class GearboxGuardError(ValueError):
    pass

@dataclass(frozen=True)
class GearDecision:
    selected_gear: str
    specialist: str
    reason: str
    guard_status: str
    return_condition: str
    expected_cost_class: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

def _norm_float(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GearboxGuardError(f"{name} must be numeric")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise GearboxGuardError(f"{name} must be in [0,1]")
    return value

def validate_formal_roster(roster: Mapping[str, Any]) -> None:
    if tuple(sorted(roster.keys())) != tuple(sorted(FORMAL_SLOTS)) or len(roster) != 3:
        raise GearboxGuardError("formal roster must remain exactly A/B/C")

def _decision(gear: str, reason: str, guard_status: str, return_condition: str) -> GearDecision:
    if gear not in VALID_GEARS:
        raise GearboxGuardError("invalid gear")
    return GearDecision(gear, SPECIALIST[gear], reason, guard_status, return_condition, COST_CLASS[gear])

def select_gear(*, risk: str, uncertainty: float, evidence_quality: float, task_complexity: float,
                reversibility: bool, contradiction: bool = False, hard_safety_conflict: bool = False,
                rollback_required: bool = False, standby: bool = False, storage_pressure_ratio: float = 0.0,
                proposed_autonomy: int = 1) -> GearDecision:
    risk = str(risk).strip().upper()
    uncertainty = _norm_float(uncertainty, name="uncertainty")
    evidence_quality = _norm_float(evidence_quality, name="evidence_quality")
    task_complexity = _norm_float(task_complexity, name="task_complexity")
    storage_pressure_ratio = _norm_float(storage_pressure_ratio, name="storage_pressure_ratio")
    if isinstance(proposed_autonomy, bool) or not isinstance(proposed_autonomy, int) or not 0 <= proposed_autonomy <= 6:
        raise GearboxGuardError("proposed_autonomy must be integer 0..6")
    if standby:
        return _decision("N", "explicit standby", "HOLD", "new valid task/control input")
    if rollback_required:
        return _decision("R", "verified rollback requested", "ROLLBACK", "verified recovery checkpoint restored")
    if hard_safety_conflict:
        return _decision("G1", "hard safety conflict", "HUMAN_GATE", "conflict resolved by deterministic policy/human gate")
    if risk in HARD_RISK:
        return _decision("G1", f"{risk.lower()} risk", "BRAKE", "risk reduced and re-evaluated")
    if contradiction:
        return _decision("G1", "contradictory inputs/evidence", "BRAKE", "contradiction independently resolved")
    if storage_pressure_ratio >= 0.95:
        return _decision("G1", "storage pressure >=95%", "HUMAN_GATE", "storage below 95% or large-write gate resolved")
    if uncertainty >= 0.60:
        return _decision("G1", "uncertainty too high", "BRAKE", "uncertainty below 0.60 with stronger evidence")
    if evidence_quality < 0.40:
        return _decision("G1", "evidence too weak", "BRAKE", "evidence quality >=0.40")
    if reversibility is not True:
        return _decision("G1", "action is not reversible", "HUMAN_GATE", "reversible plan or explicit human authorization")
    cap = 4 if storage_pressure_ratio >= 0.85 else 6
    if risk not in {"LOW", "NONE"}:
        cap = min(cap, 3)
    if uncertainty >= 0.35 or evidence_quality < 0.65:
        cap = min(cap, 3)
    if task_complexity < 0.20:
        desired = 2
    elif task_complexity < 0.45:
        desired = 3
    elif task_complexity < 0.70:
        desired = 4
    elif task_complexity < 0.90:
        desired = 5
    else:
        desired = 6
    if proposed_autonomy > 0:
        desired = min(desired, proposed_autonomy)
    selected = max(2, min(desired, cap))
    return _decision(f"G{selected}", "guarded deterministic selection", "CLEAR", "downshift on uncertainty/contradiction/risk/evidence/storage change")

def _canonical_sha256(value: object) -> str:
    import hashlib, json
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def compact_torque_state(active_state: Mapping[str, Any]) -> dict[str, Any]:
    """Transmit compact control torque, never raw chat/worksite context."""
    import copy
    compact = {key: copy.deepcopy(active_state.get(key)) for key in TORQUE_FIELDS if key in active_state}
    compact["state_fingerprint"] = _canonical_sha256({key: active_state.get(key) for key in RPM_CONTROL_FIELDS})
    return compact

def capture_owner_input_without_rpm_drop(active_state: Mapping[str, Any], owner_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fingerprint a new owner control message while preserving active mission RPM."""
    import copy, hashlib
    preserved = copy.deepcopy(dict(active_state))
    before = {key: copy.deepcopy(active_state.get(key)) for key in RPM_CONTROL_FIELDS}
    raw = str(owner_input.get("body", owner_input.get("raw_body", "")))
    meta = {
        "source": str(owner_input.get("source", "owner")),
        "kind": str(owner_input.get("kind", "control_input")),
        "body_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }
    after = {key: copy.deepcopy(preserved.get(key)) for key in RPM_CONTROL_FIELDS}
    if before != after:
        raise GearboxGuardError("incoming control dropped active mission RPM")
    return preserved, meta

def overlap_shift(*, active_state: Mapping[str, Any], from_gear: str, to_gear: str,
                  receiver_state_fingerprint: str | None = None, downshift: bool = False) -> dict[str, Any]:
    """Model clutch overlap: sender keeps torque until receiver ACK matches compact state.

    During a downshift, the lower-gear guard is engaged before higher autonomy is released.
    """
    if from_gear not in VALID_GEARS or to_gear not in VALID_GEARS or from_gear in {"N", "R"} or to_gear in {"N", "R"}:
        raise GearboxGuardError("overlap shift requires G1..G6")
    compact = compact_torque_state(active_state)
    fingerprint = compact["state_fingerprint"]
    acked = receiver_state_fingerprint == fingerprint
    if downshift:
        if int(to_gear[1:]) >= int(from_gear[1:]):
            raise GearboxGuardError("downshift target must be a lower gear")
        return {
            "from_gear": from_gear, "to_gear": to_gear, "shift_status": "DOWNSHIFT_COMPLETE" if acked else "DOWNSHIFT_OVERLAP",
            "lower_guard_engaged": True, "higher_gear_released": bool(acked), "original_atomic_work_alive": not acked,
            "compact_state": compact,
        }
    if int(to_gear[1:]) <= int(from_gear[1:]):
        raise GearboxGuardError("upshift target must be a higher gear")
    return {
        "from_gear": from_gear, "to_gear": to_gear, "shift_status": "SHIFT_COMPLETE" if acked else "CLUTCH_OVERLAP",
        "sender_torque_held": not acked, "receiver_acknowledged": bool(acked), "original_atomic_work_alive": not acked,
        "compact_state": compact,
    }
