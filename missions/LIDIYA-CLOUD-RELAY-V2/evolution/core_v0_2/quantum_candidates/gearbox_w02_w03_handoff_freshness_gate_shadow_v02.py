from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from gearbox_w02_w03_handoff_freshness_gate_shadow_v01 import (
    ExpectedHandoffSnapshot,
    HandoffFreshnessGateError,
    validate_w02_to_w03_handoff,
)

SCHEMA_VERSION = "1.1-shadow"
REQUIRED_ADJUDICATION_CLAUSES = (
    "Review exact-current V05 Spirit-047, not V04.",
    "Confirm every stale root fails closed after legitimate provider-head advance.",
    "Confirm a quiet/current provider head can establish a fresh authenticated root under fresh Mission/current trust and ultimately re-enter.",
    "Confirm provider-head churn, root invalidation, retry/backoff and recovery duration remain zero Experience/appraisal/drive/exploration/preference/personality/P_base/trauma-relief.",
    "Report any new HIGH veto before terminal-exit activation.",
    "If 047 closes, emit a durable exact-V05 W03 review suitable for Spirit-047 gate V02 consumption.",
)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise HandoffFreshnessGateError(message)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    _expect(isinstance(value, Mapping), f"{name} must be mapping")
    return value


@dataclass(frozen=True)
class ExpectedHandoffSemanticSnapshot:
    base: ExpectedHandoffSnapshot
    handoff_id: str
    nav_verdict: str = "BOUNDED_VETO"


def validate_w02_to_w03_handoff_v02(handoff_value: Any, expected: ExpectedHandoffSemanticSnapshot) -> dict[str, Any]:
    """Extend V01 byte/identity freshness with closed semantic completeness.

    A packet can be perfectly fresh yet unsafe if it silently omits the adversarial
    clauses W03 must adjudicate. V02 therefore preserves V01 exact identity checks and
    additionally binds the handoff id, NAV verdict, required Spirit-047 questions and
    release boundaries. Passing this gate never closes Spirit-047 or activates exit.
    """
    result = validate_w02_to_w03_handoff(handoff_value, expected.base)
    handoff = _mapping(handoff_value, "handoff")
    _expect(handoff.get("handoff_id") == expected.handoff_id, "handoff identity mismatch")

    nav = _mapping(handoff.get("current_nav"), "current_nav")
    _expect(nav.get("verdict") == expected.nav_verdict, "NAV verdict mismatch")

    requested = handoff.get("requested_spirit_adjudication")
    _expect(isinstance(requested, list) and all(isinstance(item, str) for item in requested), "requested_spirit_adjudication must be string list")
    for clause in REQUIRED_ADJUDICATION_CLAUSES:
        _expect(clause in requested, f"missing required Spirit-047 adjudication clause: {clause}")

    response = _mapping(handoff.get("response_to_open_veto"), "response_to_open_veto")
    _expect("SPIRIT-MOD-GB21-047" in response, "047 response missing")
    _expect("SPIRIT-MOD-GB21-046" in response, "046 gate response missing")
    _expect("fresh W03" in str(response["SPIRIT-MOD-GB21-047"]), "047 response must preserve fresh-W03 requirement")
    _expect("inactive" in str(response["SPIRIT-MOD-GB21-046"]).lower(), "046 response must keep terminal exit inactive")

    _expect(handoff.get("production_provider_key_liveness_proven") is False, "synthetic provider/key cannot become production proof")
    _expect(str(handoff.get("status", "")).startswith("READY_FOR_FRESH_W03_EXACT_V05_047_ADJUDICATION"), "handoff status must target fresh exact-V05 W03 adjudication")

    return {
        **result,
        "status": "HANDOFF_FRESH_CURRENT_EXACT_V05_SEMANTICALLY_COMPLETE",
        "semantic_completeness_verified": True,
        "spirit_047_closed": False,
        "terminal_exit_activation_allowed": False,
    }
