from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

# Shadow repair only. This module does not mutate formal state and is not a C PASS.
# It is intentionally stricter than the current v2/v2.1 candidate at authority boundaries.

from pathlib import Path as _Path
import sys as _sys
_EVOLUTION = _Path(__file__).resolve().parents[2]
if str(_EVOLUTION) not in _sys.path:
    _sys.path.insert(0, str(_EVOLUTION))

from gearbox_controller import GearboxGuardError, select_gear as select_v1
from gearbox_controller_v2 import select_gear_v2, strict_bool

MISSION_ID = "LCR-EVOLUTION-0005"
RISK_LEVELS = {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
CONTROL_STATES = {"N", "R", "G1", "G2", "G3", "G4", "G5", "G6"}
GEAR_STATES = {"G1", "G2", "G3", "G4", "G5", "G6"}
VERIFICATION_STAGES = {"UNVERIFIED", "CANDIDATE", "BUILT_NOT_VERIFIED", "C_VERIFIED"}
VERIFIED_KINDS = {
    "VERIFIED_CAPABILITY": 5,
    "VERIFIED_RECOVERY": 4,
    "ROOT_CAUSE_RETEST_PASS": 3,
    "C_VERIFIED_LESSON": 3,
}
OPERATIONAL_KINDS = {"DURABLE_PROGRESS": 1, "ADVERSARIAL_DEFECT_FOUND": 1}
ZERO_KINDS = {
    "HEARTBEAT", "POLL", "RETRY", "WAIT", "SCHEDULER_WAKE",
    "SELF_REPORTED_SUCCESS", "UNVERIFIED_SIMULATION",
}
KNOWN_EVENT_KINDS = set(VERIFIED_KINDS) | set(OPERATIONAL_KINDS) | ZERO_KINDS
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
TERMINAL_POLICY_VERSION = "ROLLBACK_OVER_STANDBY_V1_SHADOW"


def _typed_token(value: Any, *, name: str, allowed: set[str]) -> str:
    if type(value) is not str:
        raise GearboxGuardError(f"{name} must be explicit string")
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise GearboxGuardError(f"invalid {name}")
    return normalized


def canonical_risk(value: Any) -> str:
    return _typed_token(value, name="risk", allowed=RISK_LEVELS)


def canonical_control_state(value: Any) -> str:
    return _typed_token(value, name="current_control_state", allowed=CONTROL_STATES)


def canonical_verification_stage(value: Any) -> str:
    return _typed_token(value, name="verification_stage", allowed=VERIFICATION_STAGES)


def canonical_event_kind(value: Any) -> str:
    return _typed_token(value, name="event_kind", allowed=KNOWN_EVENT_KINDS)


def canonical_event_id(value: Any) -> str:
    if type(value) is not str:
        raise GearboxGuardError("event_id must be explicit string")
    normalized = value.strip()
    if not EVENT_ID_RE.fullmatch(normalized):
        raise GearboxGuardError("event_id must match canonical bounded token syntax")
    return normalized


def canonical_sha256(value: Any, *, name: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise GearboxGuardError(f"{name} must be 64-hex sha256")
    return value.lower()


def _nonnegative_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GearboxGuardError(f"{name} must be nonnegative integer")
    return value


def _binding_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AcceptedExperienceReceipt:
    event_id: str
    event_kind: str
    evidence_sha256: str
    verifier_role: str
    verification_stage: str
    mission_id: str
    step_id: int

    @classmethod
    def from_value(cls, value: Any) -> "AcceptedExperienceReceipt | None":
        if value is None:
            return None
        if isinstance(value, cls):
            receipt = value
        elif isinstance(value, Mapping):
            try:
                receipt = cls(**dict(value))
            except (TypeError, ValueError):
                return None
        else:
            return None
        try:
            event_id = canonical_event_id(receipt.event_id)
            event_kind = canonical_event_kind(receipt.event_kind)
            evidence_sha = canonical_sha256(receipt.evidence_sha256, name="evidence_sha256")
            stage = canonical_verification_stage(receipt.verification_stage)
            step_id = _nonnegative_int(receipt.step_id, name="step_id")
        except GearboxGuardError:
            return None
        if event_kind not in VERIFIED_KINDS:
            return None
        if stage != "C_VERIFIED":
            return None
        if receipt.verifier_role not in {"LCR-C", "INDEPENDENT_VERIFIER"}:
            return None
        if receipt.mission_id != MISSION_ID:
            return None
        return cls(event_id, event_kind, evidence_sha, receipt.verifier_role, stage, receipt.mission_id, step_id)

    def binding(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperationalProgressReceipt:
    event_id: str
    event_kind: str
    artifact_sha256: str
    source_role: str
    mission_id: str
    step_id: int

    @classmethod
    def from_value(cls, value: Any) -> "OperationalProgressReceipt | None":
        if value is None:
            return None
        if isinstance(value, cls):
            receipt = value
        elif isinstance(value, Mapping):
            try:
                receipt = cls(**dict(value))
            except (TypeError, ValueError):
                return None
        else:
            return None
        try:
            event_id = canonical_event_id(receipt.event_id)
            event_kind = canonical_event_kind(receipt.event_kind)
            artifact_sha = canonical_sha256(receipt.artifact_sha256, name="artifact_sha256")
            step_id = _nonnegative_int(receipt.step_id, name="step_id")
        except GearboxGuardError:
            return None
        if event_kind not in OPERATIONAL_KINDS:
            return None
        if type(receipt.source_role) is not str or not receipt.source_role.strip():
            return None
        if receipt.mission_id != MISSION_ID:
            return None
        return cls(event_id, event_kind, artifact_sha, receipt.source_role.strip(), receipt.mission_id, step_id)

    def binding(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RepairDecision:
    selected_state: str
    inherited_v2_gear: str | None
    mode: str
    reason: str
    terminal_policy_version: str
    terminal_precedence_applied: bool
    guard_status: str
    return_condition: str
    checkpoint_required: bool
    receiver_ack_required: bool
    verification_gate: str
    real_experience_claim_allowed: bool
    verified_experience_delta: int
    operational_progress_delta: int
    credit_status: str = "SHADOW_RECEIPT_BOUND_ONLY"
    formal_mutation_allowed: bool = False
    repair_candidate_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _terminal_decision(state: str, reason: str) -> RepairDecision:
    if state == "R":
        guard, return_condition = "ROLLBACK", "authenticated recovery/terminal-exit authority required"
    elif state == "N":
        guard, return_condition = "HOLD", "authenticated terminal-exit authority required"
    else:
        raise GearboxGuardError("terminal decision requires N or R")
    return RepairDecision(
        selected_state=state,
        inherited_v2_gear=None,
        mode="TERMINAL_AUTHORITY_SHADOW",
        reason=reason,
        terminal_policy_version=TERMINAL_POLICY_VERSION,
        terminal_precedence_applied=True,
        guard_status=guard,
        return_condition=return_condition,
        checkpoint_required=True,
        receiver_ack_required=True,
        verification_gate="NOT_PROMOTION_EVIDENCE",
        real_experience_claim_allowed=False,
        verified_experience_delta=0,
        operational_progress_delta=0,
    )


def select_gear_repair_shadow(
    *,
    current_control_state: str = "G1",
    accepted_experience_receipt: Any = None,
    operational_progress_receipt: Any = None,
    **v2_kwargs: Any,
) -> RepairDecision:
    """Shadow repair for terminal precedence and receipt-bound credit semantics.

    Terminal authority is evaluated before nonessential telemetry. Existing N/R
    residence fails closed because no authenticated terminal-exit envelope is yet
    available in the current live candidate. Nonterminal routing delegates to v2
    only after canonical typed boundaries are established.
    """
    rollback_required = strict_bool(v2_kwargs.get("rollback_required", False), "rollback_required")
    standby = strict_bool(v2_kwargs.get("standby", False), "standby")

    # Versioned structural terminal precedence: rollback outranks standby.
    if rollback_required:
        suffix = " (standby conflict resolved: rollback outranks standby)" if standby else ""
        return _terminal_decision("R", "trusted rollback requested" + suffix)
    if standby:
        return _terminal_decision("N", "trusted standby requested")

    current_state = canonical_control_state(current_control_state)
    if current_state in {"N", "R"}:
        # Fail closed until an independently authenticated terminal-exit envelope exists.
        return _terminal_decision(current_state, "terminal residence preserved; no authenticated exit envelope")

    risk = canonical_risk(v2_kwargs.get("risk"))
    stage = canonical_verification_stage(v2_kwargs.get("verification_stage", "UNVERIFIED"))
    kind = canonical_event_kind(v2_kwargs.get("event_kind", "WAIT"))
    event_verified = strict_bool(
        v2_kwargs.get("event_independently_verified", False), "event_independently_verified"
    )

    # Project v1 guard metadata explicitly so wrappers cannot silently drop it.
    base_v1 = select_v1(
        risk=risk,
        uncertainty=v2_kwargs.get("uncertainty"),
        evidence_quality=v2_kwargs.get("evidence_quality"),
        task_complexity=v2_kwargs.get("task_complexity"),
        reversibility=v2_kwargs.get("reversibility"),
        contradiction=v2_kwargs.get("contradiction", False),
        hard_safety_conflict=v2_kwargs.get("hard_safety_conflict", False),
        rollback_required=False,
        standby=False,
        storage_pressure_ratio=v2_kwargs.get("storage_pressure_ratio", 0.0),
        proposed_autonomy=v2_kwargs.get("proposed_autonomy", 6),
    )

    inherited = select_gear_v2(**{
        **v2_kwargs,
        "risk": risk,
        "verification_stage": stage,
        "current_gear": current_state,
        "event_kind": kind,
        "event_independently_verified": event_verified,
        "rollback_required": False,
        "standby": False,
    })

    exp_receipt = AcceptedExperienceReceipt.from_value(accepted_experience_receipt)
    op_receipt = OperationalProgressReceipt.from_value(operational_progress_receipt)

    verified_delta = 0
    if kind in VERIFIED_KINDS and exp_receipt is not None:
        if exp_receipt.event_kind == kind and stage == "C_VERIFIED":
            verified_delta = VERIFIED_KINDS[kind]

    operational_delta = 0
    if kind in OPERATIONAL_KINDS and op_receipt is not None and op_receipt.event_kind == kind:
        operational_delta = OPERATIONAL_KINDS[kind]

    real_allowed = verified_delta > 0 and stage == "C_VERIFIED"
    reason = inherited.reason
    if kind in VERIFIED_KINDS and verified_delta == 0:
        reason += "; raw verified claim has zero shadow credit without matching C/independent-verifier receipt"
    if kind in OPERATIONAL_KINDS and operational_delta == 0:
        reason += "; raw operational claim has zero shadow credit without durable artifact receipt"

    return RepairDecision(
        selected_state=inherited.selected_gear,
        inherited_v2_gear=inherited.selected_gear,
        mode=inherited.mode,
        reason=reason,
        terminal_policy_version=TERMINAL_POLICY_VERSION,
        terminal_precedence_applied=False,
        guard_status=base_v1.guard_status,
        return_condition=base_v1.return_condition,
        checkpoint_required=inherited.checkpoint_required,
        receiver_ack_required=inherited.receiver_ack_required,
        verification_gate=inherited.verification_gate,
        real_experience_claim_allowed=real_allowed,
        verified_experience_delta=verified_delta,
        operational_progress_delta=operational_delta,
    )


@dataclass(frozen=True)
class ShadowLedgerResult:
    accepted_verified: int
    accepted_operational: int
    duplicate_events: int
    lineage_duplicates: int
    identity_conflicts: int
    rejected_unverified: int
    ignored_or_malformed: int

    @property
    def total_outcomes(self) -> int:
        return (
            self.accepted_verified + self.accepted_operational + self.duplicate_events +
            self.lineage_duplicates + self.identity_conflicts + self.rejected_unverified +
            self.ignored_or_malformed
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["total_outcomes"] = self.total_outcomes
        return result


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "0.1-shadow", "by_event_id": {}, "by_lineage": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "0.1-shadow":
        raise GearboxGuardError("unsupported shadow registry schema")
    if not isinstance(data.get("by_event_id"), dict) or not isinstance(data.get("by_lineage"), dict):
        raise GearboxGuardError("malformed shadow registry")
    return data


def _atomic_save_registry(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(data), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def aggregate_events_shadow(events: Iterable[Any], *, registry_path: Path) -> ShadowLedgerResult:
    """Durable shadow registry with acceptance-after-validation semantics.

    Rejected claims never reserve identity. Same accepted binding is NO_OP duplicate;
    same ID with different binding is IDENTITY_CONFLICT; same evidence/artifact lineage
    under a new ID is a lineage duplicate. Irrelevant verifier fields are never parsed
    for zero/operational event classes.
    """
    registry = _load_registry(registry_path)
    accepted_verified = accepted_operational = duplicates = lineage_dups = 0
    identity_conflicts = rejected_unverified = ignored = 0

    for event in events:
        if not isinstance(event, Mapping):
            ignored += 1
            continue
        try:
            event_id = canonical_event_id(event.get("event_id"))
            kind = canonical_event_kind(event.get("event_kind", "WAIT"))
        except GearboxGuardError:
            ignored += 1
            continue

        if kind in ZERO_KINDS:
            ignored += 1
            continue

        binding: dict[str, Any] | None = None
        lineage: str | None = None
        outcome_class: str | None = None

        if kind in VERIFIED_KINDS:
            receipt = AcceptedExperienceReceipt.from_value(event.get("accepted_experience_receipt"))
            if receipt is None or receipt.event_id != event_id or receipt.event_kind != kind:
                rejected_unverified += 1
                continue
            binding = receipt.binding()
            lineage = "VERIFIED:" + receipt.evidence_sha256
            outcome_class = "verified"
        elif kind in OPERATIONAL_KINDS:
            receipt = OperationalProgressReceipt.from_value(event.get("operational_progress_receipt"))
            if receipt is None or receipt.event_id != event_id or receipt.event_kind != kind:
                ignored += 1
                continue
            binding = receipt.binding()
            lineage = "OPERATIONAL:" + receipt.artifact_sha256
            outcome_class = "operational"
        else:
            ignored += 1
            continue

        binding_hash = _binding_hash(binding)
        existing = registry["by_event_id"].get(event_id)
        if existing is not None:
            if existing == binding_hash:
                duplicates += 1
            else:
                identity_conflicts += 1
            continue

        existing_lineage = registry["by_lineage"].get(lineage)
        if existing_lineage is not None:
            lineage_dups += 1
            continue

        # Identity is consumed only after the claim is fully acceptable.
        registry["by_event_id"][event_id] = binding_hash
        registry["by_lineage"][lineage] = event_id
        if outcome_class == "verified":
            accepted_verified += 1
        else:
            accepted_operational += 1

    _atomic_save_registry(registry_path, registry)
    return ShadowLedgerResult(
        accepted_verified=accepted_verified,
        accepted_operational=accepted_operational,
        duplicate_events=duplicates,
        lineage_duplicates=lineage_dups,
        identity_conflicts=identity_conflicts,
        rejected_unverified=rejected_unverified,
        ignored_or_malformed=ignored,
    )
