from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gearbox_w02_w03_handoff_freshness_gate_shadow_v01 import (
    ExpectedHandoffSnapshot,
    _expect,
    _mapping,
    _sha,
    validate_w02_to_w03_handoff,
)

SCHEMA_VERSION = "1.3-shadow"
REQUIRED_ADJUDICATION_CLAUSES_V04 = (
    "Review exact-current V05 Spirit-047, not V04.",
    "Reject every older W02/NAV handoff and bind this review to current W02-2108 plus current NAV-2108 synthesis.",
    "Confirm every stale root fails closed after legitimate provider-head advance.",
    "Confirm a quiet/current provider head can establish a fresh authenticated root under fresh Mission/current trust and ultimately re-enter.",
    "Confirm provider-head churn, root invalidation, retry/backoff and recovery duration remain zero Experience/appraisal/drive/exploration/preference/personality/P_base/trauma-relief.",
    "Report any new higher HIGH veto before terminal-exit activation.",
    "If 047 closes, emit a durable exact-V05 W03 review suitable for Spirit-047 review acceptance gate V03 consumption.",
)


@dataclass(frozen=True)
class ExpectedHandoffV04Snapshot:
    base: ExpectedHandoffSnapshot
    handoff_id: str
    spirit_gate_test_sha: str
    spirit_gate_contract_sha: str
    spirit_gate_workflow_sha: str
    spirit_gate_workflow_commit: str
    prior_handoff_gate_v03_source_sha: str
    prior_handoff_gate_v03_test_sha: str
    prior_handoff_gate_v03_contract_sha: str
    prior_handoff_gate_v03_workflow_sha: str
    nav_verdict: str = "BOUNDED_VETO"


def validate_w02_to_w03_handoff_v04(handoff_value: Any, expected: ExpectedHandoffV04Snapshot) -> dict[str, Any]:
    """Validate an exact-current W02-2108/NAV-2108 packet for independent V05 Spirit review.

    V04 repairs the stale-current-pointer defect in the prior 2108 packet. It does not
    decide Spirit-047, activate terminal exit, or create any formal/learning effect.
    """
    result = validate_w02_to_w03_handoff(handoff_value, expected.base)
    handoff = _mapping(handoff_value, "handoff")
    _expect(handoff.get("schema_version") == "1.4", "V04 requires durable handoff schema 1.4")
    _expect(handoff.get("handoff_id") == expected.handoff_id, "handoff identity mismatch")

    nav = _mapping(handoff.get("current_nav"), "current_nav")
    _expect(nav.get("verdict") == expected.nav_verdict, "NAV verdict mismatch")

    gate = _mapping(handoff.get("current_spirit_gate"), "current_spirit_gate")
    _expect(gate.get("version") == "V03", "Spirit review-acceptance gate must remain V03")
    _expect(_sha(gate.get("test_git_blob_sha"), "Spirit gate test") == _sha(expected.spirit_gate_test_sha, "expected Spirit gate test"), "Spirit gate test substitution")
    _expect(_sha(gate.get("contract_git_blob_sha"), "Spirit gate contract") == _sha(expected.spirit_gate_contract_sha, "expected Spirit gate contract"), "Spirit gate contract substitution")
    _expect(_sha(gate.get("workflow_git_blob_sha"), "Spirit gate workflow") == _sha(expected.spirit_gate_workflow_sha, "expected Spirit gate workflow"), "Spirit gate workflow substitution")
    _expect(_sha(gate.get("workflow_update_commit"), "Spirit gate workflow commit") == _sha(expected.spirit_gate_workflow_commit, "expected Spirit gate workflow commit"), "Spirit gate workflow commit substitution")

    freshness = _mapping(handoff.get("handoff_freshness_gate"), "handoff_freshness_gate")
    _expect(freshness.get("version") == "V04", "handoff freshness gate must be V04")
    _expect(_sha(freshness.get("prior_v03_source_git_blob_sha"), "prior V03 source") == _sha(expected.prior_handoff_gate_v03_source_sha, "expected prior V03 source"), "prior V03 source substitution")
    _expect(_sha(freshness.get("prior_v03_test_git_blob_sha"), "prior V03 test") == _sha(expected.prior_handoff_gate_v03_test_sha, "expected prior V03 test"), "prior V03 test substitution")
    _expect(_sha(freshness.get("prior_v03_contract_git_blob_sha"), "prior V03 contract") == _sha(expected.prior_handoff_gate_v03_contract_sha, "expected prior V03 contract"), "prior V03 contract substitution")
    _expect(_sha(freshness.get("prior_v03_workflow_git_blob_sha"), "prior V03 workflow") == _sha(expected.prior_handoff_gate_v03_workflow_sha, "expected prior V03 workflow"), "prior V03 workflow substitution")

    requested = handoff.get("requested_spirit_adjudication")
    _expect(isinstance(requested, list) and all(isinstance(item, str) for item in requested), "requested_spirit_adjudication must be string list")
    for clause in REQUIRED_ADJUDICATION_CLAUSES_V04:
        _expect(clause in requested, f"missing required V04 adjudication clause: {clause}")

    response = _mapping(handoff.get("response_to_open_veto"), "response_to_open_veto")
    _expect("fresh W03" in str(response.get("SPIRIT-MOD-GB21-047", "")), "047 response must preserve fresh-W03 requirement")
    response_046 = str(response.get("SPIRIT-MOD-GB21-046", ""))
    _expect("inactive" in response_046.lower(), "046 must remain inactive")
    _expect("V03" in response_046, "046 activation boundary must name Spirit V03 consumer gate")

    zero = _mapping(handoff.get("zero_learning_boundary"), "zero_learning_boundary")
    _expect(zero.get("handoff_freshness_is_experience") is False, "handoff freshness cannot become Experience")
    _expect(handoff.get("formal_c_pass_claimed") is False, "formal C claim forbidden")
    _expect(handoff.get("production_provider_key_liveness_proven") is False, "synthetic provider/key cannot become production proof")
    _expect(str(handoff.get("status", "")).startswith("READY_FOR_FRESH_W03_EXACT_V05_047_ADJUDICATION_W02_2108_NAV_2108"), "status must bind current W02-2108/NAV-2108")

    return {
        **result,
        "status": "HANDOFF_V04_FRESH_CURRENT_W02_2108_NAV_2108_EXACT_V05",
        "semantic_completeness_verified": True,
        "spirit_review_acceptance_gate_v03_bound": True,
        "spirit_047_closed": False,
        "terminal_exit_activation_allowed": False,
        "formal_effect": "NONE",
        "experience_delta": 0,
        "personality_delta": 0,
        "p_base_mutation_allowed": False,
    }
