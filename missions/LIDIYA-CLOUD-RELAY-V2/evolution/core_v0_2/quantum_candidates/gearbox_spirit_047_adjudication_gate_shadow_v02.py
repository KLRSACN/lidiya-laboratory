from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import re

MISSION_ID = "LCR-EVOLUTION-0005"
STEP_ID = 9
CURRENT_CANDIDATE = "V05"
REQUIRED_VETO = "SPIRIT-MOD-GB21-047"
REQUIRED_EVIDENCE_STATUS = "EXACT_CURRENT_NONFORMAL_EXECUTABLE_EVIDENCE_BOUND"
EXPECTED_V05_SOURCE_SHA = "9aaf3ad9f673944d548e2cd880c9286b98e72704"
EXPECTED_V05_TEST_SHA = "a4c98981561cf8c310c66c03367aa8fbf3954d61"
EXPECTED_V05_CONTRACT_SHA = "df4753a9eaa7d734afb81a7e32d7efb3fa6617b7"
EXPECTED_RUN_ID = 32524738088
EXPECTED_JOB_ID = 96904287434
EXPECTED_TOTAL_REGRESSIONS = 27
HEX40 = re.compile(r"^[0-9a-f]{40}$")

class SpiritAdjudicationGateError(ValueError):
    pass

@dataclass(frozen=True)
class Spirit047Adjudication:
    mission_id: str
    step_id: int
    candidate_version: str
    spirit_review_id: str
    spirit_review_blob_sha: str
    reviewed_candidate_version: str
    veto_id: str
    disposition: str
    higher_high_veto_open: bool
    evidence_binding_status: str
    v05_source_sha: str
    v05_test_sha: str
    v05_contract_sha: str
    workflow_run_id: int
    workflow_job_id: int
    executed_regression_total: int
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
        if not isinstance(x.spirit_review_blob_sha, str) or not HEX40.fullmatch(x.spirit_review_blob_sha):
            raise SpiritAdjudicationGateError("durable Spirit review blob identity required")
        if x.veto_id != REQUIRED_VETO or x.disposition != "CLOSED_FOR_NONFORMAL_TERMINAL_EXIT_ENGINEERING":
            raise SpiritAdjudicationGateError("Spirit 047 remains open")
        if type(x.higher_high_veto_open) is not bool or x.higher_high_veto_open:
            raise SpiritAdjudicationGateError("higher HIGH veto blocks terminal activation")
        if x.evidence_binding_status != REQUIRED_EVIDENCE_STATUS:
            raise SpiritAdjudicationGateError("exact-current evidence binding not consumed")
        expected = (EXPECTED_V05_SOURCE_SHA, EXPECTED_V05_TEST_SHA, EXPECTED_V05_CONTRACT_SHA)
        actual = (x.v05_source_sha, x.v05_test_sha, x.v05_contract_sha)
        if actual != expected:
            raise SpiritAdjudicationGateError("V05 exact-byte identity mismatch")
        if type(x.workflow_run_id) is not int or type(x.workflow_job_id) is not int:
            raise SpiritAdjudicationGateError("workflow evidence ids must be integers")
        if x.workflow_run_id != EXPECTED_RUN_ID or x.workflow_job_id != EXPECTED_JOB_ID:
            raise SpiritAdjudicationGateError("workflow evidence identity mismatch")
        if type(x.executed_regression_total) is not int or x.executed_regression_total != EXPECTED_TOTAL_REGRESSIONS:
            raise SpiritAdjudicationGateError("V05 regression evidence count mismatch")
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
        "spirit_review_blob_sha": x.spirit_review_blob_sha,
        "bound_workflow_run_id": x.workflow_run_id,
        "bound_workflow_job_id": x.workflow_job_id,
        "experience_delta": 0,
        "appraisal_delta": 0,
        "drive_delta": 0,
        "exploration_delta": 0,
        "preference_delta": 0,
        "personality_delta": 0,
        "trauma_relief_delta": 0,
        "p_base_mutation_allowed": False,
        "formal_effect": "NONE",
        "formal_c_verification": "NOT_CLAIMED",
    }
