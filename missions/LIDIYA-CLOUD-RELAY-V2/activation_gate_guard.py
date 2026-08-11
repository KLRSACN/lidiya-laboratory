from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class GateError(ValueError):
    pass


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    code: str
    reason: str


TERMINAL = {"CONSUMED_CLOSED", "REVOKED"}


def validate_authorization(
    auth: dict[str, Any],
    *,
    expected_mission: str,
    launcher_path: str,
    validation_pr: int,
) -> None:
    if auth.get("mission_id") != expected_mission:
        raise GateError("mission mismatch")
    if auth.get("authorization_type") != "ONE_TIME_ACTIVATION_GATE":
        raise GateError("authorization is not one-time")
    carrier = auth.get("validation_carrier") or {}
    if carrier.get("pull_request") != validation_pr:
        raise GateError("validation PR mismatch")
    if carrier.get("merge_authorized") is not False:
        raise GateError("validation carrier must not authorize merge")
    allowed = auth.get("allowed") or {}
    scopes = allowed.get("default_branch_write_scope") or []
    if launcher_path not in scopes:
        raise GateError("launcher path is outside authorized scope")


def evaluate_gate(ledger: dict[str, Any] | None, *, github_run_id: str) -> GateDecision:
    if not ledger:
        return GateDecision(True, "READY_TO_CLAIM", "No prior claim exists.")
    status = ledger.get("status")
    owner = str(ledger.get("claimed_by_github_run_id") or "")
    if status in TERMINAL:
        return GateDecision(False, f"BLOCKED_{status}", "One-time gate cannot be reused.")
    if status == "CLAIMED":
        if owner == str(github_run_id):
            return GateDecision(True, "CLAIMED_BY_THIS_RUN", "Same workflow run may continue the claimed gate.")
        return GateDecision(False, "BLOCKED_ACTIVE_CLAIM", "Another workflow run already owns the gate.")
    if status in (None, "AUTHORIZED", "READY"):
        return GateDecision(True, "READY_TO_CLAIM", "Gate is authorized and unconsumed.")
    return GateDecision(False, "BLOCKED_UNKNOWN_STATE", f"Unsupported gate status: {status!r}")


def claim_gate(*, mission_id: str, github_run_id: str, claimed_at: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "mission_id": mission_id,
        "status": "CLAIMED",
        "claimed_by_github_run_id": str(github_run_id),
        "claimed_at": claimed_at,
        "reusable": False,
    }


def close_gate(
    ledger: dict[str, Any],
    *,
    github_run_id: str,
    verified_roundtrip: bool,
    metabolic_closed: bool,
    closure_evidence: str,
    closed_at: str,
) -> dict[str, Any]:
    decision = evaluate_gate(ledger, github_run_id=str(github_run_id))
    if not decision.allowed or decision.code != "CLAIMED_BY_THIS_RUN":
        raise GateError(decision.code)
    if not verified_roundtrip:
        raise GateError("roundtrip must be verified before closure")
    if not metabolic_closed:
        raise GateError("metabolic closure must complete before consuming gate")
    if not closure_evidence:
        raise GateError("closure evidence is required")
    closed = dict(ledger)
    closed.update(
        {
            "status": "CONSUMED_CLOSED",
            "consumed_by_github_run_id": str(github_run_id),
            "closed_at": closed_at,
            "closure_evidence": closure_evidence,
            "reusable": False,
        }
    )
    return closed
