from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA_VERSION = "1.0-shadow"
MISSION_ID = "LCR-EVOLUTION-0005"
STEP_ID = 9
VETO_ID = "SPIRIT-MOD-GB21-047"
REQUIRED_REGRESSION = "MOVING_PROVIDER_HEAD_REESTABLISHMENT_NON_TERMINAL_AB"
ZERO_LEARNING_KEYS = (
    "provider_head_churn_is_experience",
    "retry_backoff_is_experience",
    "recovery_duration_is_experience",
    "appraisal_delta",
    "drive_delta",
    "exploration_delta",
    "preference_delta",
    "personality_delta",
    "trauma_relief_delta",
    "p_base_mutation_allowed",
)


class HandoffFreshnessGateError(ValueError):
    pass


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise HandoffFreshnessGateError(message)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    _expect(isinstance(value, Mapping), f"{name} must be mapping")
    return value


def _sha(value: Any, name: str) -> str:
    _expect(isinstance(value, str) and len(value) == 40 and all(c in "0123456789abcdefABCDEF" for c in value), f"{name} must be 40-hex Git blob SHA")
    return value.lower()


def _digest(value: Any, name: str) -> str:
    _expect(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdefABCDEF" for c in value), f"{name} must be 64-hex SHA256")
    return value.lower()


@dataclass(frozen=True)
class ExpectedHandoffSnapshot:
    mission_state_sha: str
    w02_review_id: str
    w02_review_sha: str
    nav_synthesis_id: str
    nav_sha: str
    v05_source_sha: str
    v05_test_sha: str
    v05_contract_sha: str
    spirit_gate_version: str
    spirit_gate_source_sha: str
    workflow_run_id: int
    job_id: int
    artifact_id: int
    artifact_zip_sha256: str


def validate_w02_to_w03_handoff(handoff_value: Any, expected: ExpectedHandoffSnapshot) -> dict[str, Any]:
    """Fail closed unless the durable W02->W03 packet exactly matches fresh independent expectations.

    This is non-formal shadow evidence plumbing only. It cannot close Spirit-047, activate
    terminal exit, mutate formal state, or claim production provider/key trust.
    """
    handoff = _mapping(handoff_value, "handoff")
    _expect(handoff.get("schema_version") in {"1.2", "1.3"}, "unsupported handoff schema")
    _expect(handoff.get("source") == "W02-QUANTUM" and handoff.get("target") == "W03-SPIRIT", "handoff route mismatch")
    _expect(handoff.get("formal_effect") == "NONE_NONFORMAL_REVIEW_EVIDENCE_ONLY", "formal effect forbidden")
    _expect(handoff.get("formal_c_pass_claimed") is False, "formal C claim forbidden")

    mission = _mapping(handoff.get("mission_state"), "mission_state")
    _expect(_sha(mission.get("git_blob_sha"), "mission_state.git_blob_sha") == _sha(expected.mission_state_sha, "expected mission_state_sha"), "mission snapshot mismatch")
    _expect(mission.get("step_id") == STEP_ID and mission.get("status") == "STEP_DONE" and mission.get("current_role") == "LCR-A", "formal baseline mismatch")
    _expect(mission.get("pending_packet") is None and mission.get("v1") == "VERIFIED_PASS", "formal baseline boundary mismatch")

    target = _mapping(handoff.get("review_target"), "review_target")
    _expect(target.get("veto") == VETO_ID and target.get("candidate_version") == "V05", "wrong Spirit review target")
    _expect(target.get("required_regression") == REQUIRED_REGRESSION, "wrong required regression")

    w02 = _mapping(handoff.get("current_w02_review"), "current_w02_review")
    _expect(w02.get("review_id") == expected.w02_review_id, "stale W02 review id")
    _expect(_sha(w02.get("git_blob_sha"), "current_w02_review.git_blob_sha") == _sha(expected.w02_review_sha, "expected w02_review_sha"), "stale W02 review blob")

    nav = _mapping(handoff.get("current_nav"), "current_nav")
    _expect(nav.get("synthesis_id") == expected.nav_synthesis_id, "stale NAV synthesis id")
    _expect(_sha(nav.get("git_blob_sha"), "current_nav.git_blob_sha") == _sha(expected.nav_sha, "expected nav_sha"), "stale NAV blob")

    candidate = _mapping(handoff.get("exact_current_candidate"), "exact_current_candidate")
    _expect(_sha(candidate.get("source_git_blob_sha"), "candidate source") == _sha(expected.v05_source_sha, "expected source"), "V05 source substitution")
    _expect(_sha(candidate.get("test_git_blob_sha"), "candidate test") == _sha(expected.v05_test_sha, "expected test"), "V05 test substitution")
    _expect(_sha(candidate.get("contract_git_blob_sha"), "candidate contract") == _sha(expected.v05_contract_sha, "expected contract"), "V05 contract substitution")

    gate = _mapping(handoff.get("current_spirit_gate"), "current_spirit_gate")
    _expect(gate.get("version") == expected.spirit_gate_version, "Spirit gate version mismatch")
    _expect(_sha(gate.get("source_git_blob_sha"), "Spirit gate source") == _sha(expected.spirit_gate_source_sha, "expected gate source"), "Spirit gate substitution")

    evidence = _mapping(handoff.get("visible_executable_evidence"), "visible_executable_evidence")
    _expect(evidence.get("workflow_run_id") == expected.workflow_run_id, "workflow run substitution")
    _expect(evidence.get("job_id") == expected.job_id and evidence.get("job_conclusion") == "success", "job identity/conclusion mismatch")
    _expect(evidence.get("artifact_id") == expected.artifact_id, "artifact substitution")
    _expect(_digest(evidence.get("artifact_zip_sha256"), "artifact_zip_sha256") == _digest(expected.artifact_zip_sha256, "expected artifact_zip_sha256"), "artifact digest substitution")
    counts = _mapping(evidence.get("regression_counts"), "regression_counts")
    _expect(counts.get("V01") == "9/9" and counts.get("V03") == "9/9" and counts.get("V04") == "5/5" and counts.get("V05") == "4/4" and counts.get("total") == "27/27", "incomplete moving-head evidence")

    zero = _mapping(handoff.get("zero_learning_boundary"), "zero_learning_boundary")
    _expect(zero.get("provider_head_churn_is_experience") is False, "provider churn cannot be Experience")
    _expect(zero.get("retry_backoff_is_experience") is False, "retry/backoff cannot be Experience")
    _expect(zero.get("recovery_duration_is_experience") is False, "recovery duration cannot be Experience")
    for key in ("appraisal_delta", "drive_delta", "exploration_delta", "preference_delta", "personality_delta", "trauma_relief_delta"):
        _expect(zero.get(key) == 0, f"{key} must remain zero")
    _expect(zero.get("p_base_mutation_allowed") is False, "P_base mutation forbidden")

    return {
        "status": "HANDOFF_FRESH_CURRENT_EXACT_V05",
        "spirit_047_closed": False,
        "terminal_exit_activation_allowed": False,
        "formal_effect": "NONE",
        "experience_delta": 0,
        "personality_delta": 0,
        "p_base_mutation_allowed": False,
    }
