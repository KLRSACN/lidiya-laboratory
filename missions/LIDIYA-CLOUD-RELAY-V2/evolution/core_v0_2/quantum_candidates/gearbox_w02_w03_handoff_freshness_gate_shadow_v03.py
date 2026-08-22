from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from gearbox_w02_w03_handoff_freshness_gate_shadow_v01 import (
    ExpectedHandoffSnapshot,
    HandoffFreshnessGateError,
    _expect,
    _mapping,
    _sha,
    validate_w02_to_w03_handoff,
)

SCHEMA_VERSION = "1.2-shadow"
REQUIRED_ADJUDICATION_CLAUSES_V03 = (
    "Review exact-current V05 Spirit-047, not V04.",
    "Reject every older W02/NAV handoff and bind this review to current W02-2008 plus current NAV-2008 synthesis.",
    "Confirm every stale root fails closed after legitimate provider-head advance.",
    "Confirm a quiet/current provider head can establish a fresh authenticated root under fresh Mission/current trust and ultimately re-enter.",
    "Confirm provider-head churn, root invalidation, retry/backoff and recovery duration remain zero Experience/appraisal/drive/exploration/preference/personality/P_base/trauma-relief.",
    "Report any new higher HIGH veto before terminal-exit activation.",
    "If 047 closes, emit a durable exact-V05 W03 review suitable for Spirit-047 review acceptance gate V03 consumption.",
)


@dataclass(frozen=True)
class ExpectedHandoffV03Snapshot:
    base: ExpectedHandoffSnapshot
    handoff_id: str
    spirit_gate_test_sha: str
    spirit_gate_contract_sha: str
    spirit_gate_workflow_sha: str
    spirit_gate_workflow_commit: str
    nav_verdict: str = "BOUNDED_VETO"


def validate_w02_to_w03_handoff_v03(handoff_value: Any, expected: ExpectedHandoffV03Snapshot) -> dict[str, Any]:
    """Validate the exact current W02->W03 packet for independent Spirit-047 V05 adjudication.

    V03 closes two evidence-plumbing holes at once: the packet must bind the current
    W02/NAV identities and it must bind the *review-acceptance gate V03* code, tests,
    contract and workflow rather than an older V02 consumer. Passing remains a
    non-formal packet-freshness result only; W03 independently authors any 047 verdict.
    """
    result = validate_w02_to_w03_handoff(handoff_value, expected.base)
    handoff = _mapping(handoff_value, "handoff")
    _expect(handoff.get("schema_version") == "1.4", "V03 requires current handoff schema 1.4")
    _expect(handoff.get("handoff_id") == expected.handoff_id, "handoff identity mismatch")

    nav = _mapping(handoff.get("current_nav"), "current_nav")
    _expect(nav.get("verdict") == expected.nav_verdict, "NAV verdict mismatch")

    gate = _mapping(handoff.get("current_spirit_gate"), "current_spirit_gate")
    _expect(gate.get("version") == "V03", "Spirit review-acceptance gate must be V03")
    _expect(_sha(gate.get("test_git_blob_sha"), "Spirit gate test") == _sha(expected.spirit_gate_test_sha, "expected Spirit gate test"), "Spirit gate test substitution")
    _expect(_sha(gate.get("contract_git_blob_sha"), "Spirit gate contract") == _sha(expected.spirit_gate_contract_sha, "expected Spirit gate contract"), "Spirit gate contract substitution")
    _expect(_sha(gate.get("workflow_git_blob_sha"), "Spirit gate workflow") == _sha(expected.spirit_gate_workflow_sha, "expected Spirit gate workflow"), "Spirit gate workflow substitution")
    _expect(_sha(gate.get("workflow_update_commit"), "Spirit gate workflow commit") == _sha(expected.spirit_gate_workflow_commit, "expected Spirit gate workflow commit"), "Spirit gate workflow commit substitution")

    requested = handoff.get("requested_spirit_adjudication")
    _expect(isinstance(requested, list) and all(isinstance(item, str) for item in requested), "requested_spirit_adjudication must be string list")
    for clause in REQUIRED_ADJUDICATION_CLAUSES_V03:
        _expect(clause in requested, f"missing required V03 adjudication clause: {clause}")

    response = _mapping(handoff.get("response_to_open_veto"), "response_to_open_veto")
    _expect("fresh W03" in str(response.get("SPIRIT-MOD-GB21-047", "")), "047 response must preserve fresh-W03 requirement")
    response_046 = str(response.get("SPIRIT-MOD-GB21-046", ""))
    _expect("inactive" in response_046.lower(), "046 must remain inactive")
    _expect("V03" in response_046, "046 activation boundary must name V03 consumer gate")

    zero = _mapping(handoff.get("zero_learning_boundary"), "zero_learning_boundary")
    _expect(zero.get("handoff_freshness_is_experience") is False, "handoff freshness cannot become Experience")
    _expect(handoff.get("formal_c_pass_claimed") is False, "formal C claim forbidden")
    _expect(handoff.get("production_provider_key_liveness_proven") is False, "synthetic provider/key cannot become production proof")
    _expect(str(handoff.get("status", "")).startswith("READY_FOR_FRESH_W03_EXACT_V05_047_ADJUDICATION_W02_2008"), "status must bind W02-2008 fresh adjudication")

    return {
        **result,
        "status": "HANDOFF_V03_FRESH_CURRENT_W02_2008_NAV_2008_EXACT_V05",
        "semantic_completeness_verified": True,
        "review_acceptance_gate_v03_bound": True,
        "spirit_047_closed": False,
        "terminal_exit_activation_allowed": False,
        "formal_effect": "NONE",
        "experience_delta": 0,
        "personality_delta": 0,
        "p_base_mutation_allowed": False,
    }
