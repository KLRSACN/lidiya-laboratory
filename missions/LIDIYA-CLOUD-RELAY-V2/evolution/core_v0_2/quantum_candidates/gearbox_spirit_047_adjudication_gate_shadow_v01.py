from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

MISSION_ID = "LCR-EVOLUTION-0005"
STEP_ID = 9
CURRENT_CANDIDATE = "V05"
REQUIRED_VETO = "SPIRIT-MOD-GB21-047"
REQUIRED_EVIDENCE_STATUS = "EXACT_CURRENT_NONFORMAL_EXECUTABLE_EVIDENCE_BOUND"


class SpiritAdjudicationGateError(ValueError):
    pass


@dataclass(frozen=True)
class Spirit047Adjudication:
    mission_id: str
    step_id: int
    candidate_version: str
    spirit_review_id: str
    reviewed_candidate_version: str
    veto_id: str
    disposition: str
    higher_high_veto_open: bool
    evidence_binding_status: str
    terminal_exit_activation_allowed: bool
    formal_effect: str = "NONE"
    c_pass_claimed: bool = False

    @classmethod
    def verify_for_terminal_activation(cls, value: Any) -> "Spirit047Adjudication":
        if not isinstance(value, Mapping):
            raise SpiritAdjudicationGateError("fresh Spirit adjudication mapping required")
        try:
            x = cls(**dict(value))
        except TypeError as exc:
            raise SpiritAdjudicationGateError("malformed Spirit adjudication") from exc
        if x.mission_id != MISSION_ID or x.step_id != STEP_ID:
            raise SpiritAdjudicationGateError("Spirit adjudication mission/step mismatch")
        if x.candidate_version != CURRENT_CANDIDATE or x.reviewed_candidate_version != CURRENT_CANDIDATE:
            raise SpiritAdjudicationGateError("Spirit adjudication is not exact-current V05")
        if not isinstance(x.spirit_review_id, str) or not x.spirit_review_id.strip():
            raise SpiritAdjudicationGateError("Spirit review id required")
        if x.veto_id != REQUIRED_VETO:
            raise SpiritAdjudicationGateError("wrong Spirit veto adjudication")
        if x.disposition != "CLOSED_FOR_NONFORMAL_TERMINAL_EXIT_ENGINEERING":
            raise SpiritAdjudicationGateError("Spirit 047 remains open")
        if type(x.higher_high_veto_open) is not bool or x.higher_high_veto_open:
            raise SpiritAdjudicationGateError("higher HIGH veto blocks terminal activation")
        if x.evidence_binding_status != REQUIRED_EVIDENCE_STATUS:
            raise SpiritAdjudicationGateError("exact-current evidence binding not consumed")
        if x.terminal_exit_activation_allowed is not True:
            raise SpiritAdjudicationGateError("terminal exit activation not explicitly allowed")
        if x.formal_effect != "NONE" or x.c_pass_claimed is not False:
            raise SpiritAdjudicationGateError("non-formal boundary violated")
        return x


def terminal_exit_engineering_gate(value: Any) -> dict[str, Any]:
    x = Spirit047Adjudication.verify_for_terminal_activation(value)
    return {
        "gate": "OPEN_FOR_NONFORMAL_TERMINAL_EXIT_ENGINEERING",
        "candidate_version": x.candidate_version,
        "spirit_review_id": x.spirit_review_id,
        "experience_delta": 0,
        "personality_delta": 0,
        "p_base_mutation_allowed": False,
        "formal_effect": "NONE",
        "formal_c_verification": "NOT_CLAIMED",
    }
