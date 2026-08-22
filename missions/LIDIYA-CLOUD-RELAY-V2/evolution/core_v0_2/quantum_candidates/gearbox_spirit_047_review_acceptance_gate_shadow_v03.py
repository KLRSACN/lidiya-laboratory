from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

MISSION_ID = "LCR-EVOLUTION-0005"
STEP_ID = 9
EXPECTED_VETO = "SPIRIT-MOD-GB21-047"
EXPECTED_CANDIDATE_VERSION = "V05"
EXPECTED_V05_SOURCE_SHA = "9aaf3ad9f673944d548e2cd880c9286b98e72704"
EXPECTED_V05_TEST_SHA = "a4c98981561cf8c310c66c03367aa8fbf3954d61"
EXPECTED_V05_CONTRACT_SHA = "df4753a9eaa7d734afb81a7e32d7efb3fa6617b7"
EXPECTED_RUN_ID = 32524738088
EXPECTED_JOB_ID = 96904287434
EXPECTED_ARTIFACT_ID = 9461767094
EXPECTED_ARTIFACT_SHA256 = "c3bba5ce8ca2b90ca9ec78ed0f43aa9bc3aeaef903979e9e7d8808c715bd8429"
EXPECTED_TOTAL_REGRESSIONS = 27


class Spirit047AcceptanceError(ValueError):
    pass


@dataclass(frozen=True)
class Spirit047AcceptanceResult:
    accepted_for_terminal_exit_engineering: bool
    formal_effect: str = "NONE"
    formal_c_pass_claimed: bool = False
    experience_delta: int = 0
    appraisal_delta: int = 0
    drive_delta: int = 0
    exploration_delta: int = 0
    preference_delta: int = 0
    personality_delta: int = 0
    trauma_relief_delta: int = 0
    p_base_mutation_allowed: bool = False


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Spirit047AcceptanceError(f"{name} must be mapping")
    return value


def _require_exact(mapping: Mapping[str, Any], key: str, expected: Any) -> None:
    if mapping.get(key) != expected:
        raise Spirit047AcceptanceError(f"{key} mismatch")


def validate_spirit_047_exact_v05_review(review: Any) -> Spirit047AcceptanceResult:
    """Fail-closed consumer gate for a future W03 exact-V05 Spirit-047 closure.

    This gate does not decide Spirit-047. It only permits terminal-exit engineering
    when an independently authored durable W03 review is explicitly exact-current,
    evidence-bound, zero-learning, and free of any higher HIGH veto.
    """
    review = _require_mapping(review, "review")
    _require_exact(review, "mission_id", MISSION_ID)
    _require_exact(review, "step_id", STEP_ID)
    _require_exact(review, "reviewer", "W03-SPIRIT")
    _require_exact(review, "candidate_version", EXPECTED_CANDIDATE_VERSION)
    _require_exact(review, "adjudicated_veto", EXPECTED_VETO)
    _require_exact(review, "veto_disposition", "CLOSED_FOR_SHADOW_ENGINEERING")
    _require_exact(review, "terminal_exit_engineering_allowed", True)
    _require_exact(review, "formal_c_pass_claimed", False)

    hashes = _require_mapping(review.get("candidate_hashes"), "candidate_hashes")
    _require_exact(hashes, "source_git_blob_sha", EXPECTED_V05_SOURCE_SHA)
    _require_exact(hashes, "test_git_blob_sha", EXPECTED_V05_TEST_SHA)
    _require_exact(hashes, "contract_git_blob_sha", EXPECTED_V05_CONTRACT_SHA)

    evidence = _require_mapping(review.get("visible_executable_evidence"), "visible_executable_evidence")
    _require_exact(evidence, "workflow_run_id", EXPECTED_RUN_ID)
    _require_exact(evidence, "job_id", EXPECTED_JOB_ID)
    _require_exact(evidence, "artifact_id", EXPECTED_ARTIFACT_ID)
    _require_exact(evidence, "artifact_zip_sha256", EXPECTED_ARTIFACT_SHA256)
    _require_exact(evidence, "job_conclusion", "success")
    _require_exact(evidence, "total_regressions_passed", EXPECTED_TOTAL_REGRESSIONS)
    _require_exact(evidence, "total_regressions_expected", EXPECTED_TOTAL_REGRESSIONS)

    if review.get("higher_high_vetoes") not in ([], ()):  # exact absence required
        raise Spirit047AcceptanceError("higher HIGH veto remains")

    assertions = _require_mapping(review.get("required_assertions"), "required_assertions")
    for key in (
        "every_stale_root_fails_closed",
        "current_head_can_reestablish_fresh_authenticated_root",
        "eventual_nonterminal_reentry_demonstrated",
        "fresh_mission_authority_precedence",
        "no_stale_pressure_or_terminal_hold_carryover",
        "provider_churn_zero_experience",
        "retry_backoff_zero_experience",
        "recovery_duration_zero_experience",
        "cognitive_personality_state_equal_when_verified_experience_equal",
    ):
        _require_exact(assertions, key, True)

    zero = _require_mapping(review.get("zero_learning_boundary"), "zero_learning_boundary")
    for key in (
        "experience_delta", "appraisal_delta", "drive_delta", "exploration_delta",
        "preference_delta", "personality_delta", "trauma_relief_delta",
    ):
        _require_exact(zero, key, 0)
    _require_exact(zero, "p_base_mutation_allowed", False)

    if review.get("production_provider_key_liveness_proven") is not False:
        raise Spirit047AcceptanceError("synthetic evidence cannot prove production provider/key liveness")

    return Spirit047AcceptanceResult(accepted_for_terminal_exit_engineering=True)
