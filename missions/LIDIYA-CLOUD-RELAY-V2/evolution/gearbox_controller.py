from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

FORMAL_SLOTS = ("LCR-A", "LCR-B", "LCR-C")
VALID_GEARS = ("N", "R", "G1", "G2", "G3", "G4", "G5", "G6")
HARD_RISK = {"HIGH", "CRITICAL"}
COST_CLASS = {"N": "ZERO", "R": "ZERO", "G1": "TINY", "G2": "SMALL", "G3": "SMALL", "G4": "SMALL", "G5": "MEDIUM", "G6": "REFERENCE"}
SPECIALIST = {"N": "STANDBY", "R": "ROLLBACK_CONTROLLER", "G1": "DETERMINISTIC_START_BRAKE", "G2": "ROUTER", "G3": "EVIDENCE_METABOLISM", "G4": "ROUTINE_PLANNER", "G5": "INTEGRATOR_2B", "G6": "TEACHER_REFERENCE"}

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
