from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from pathlib import Path as _Path
import sys as _sys

_HERE = _Path(__file__).resolve().parent
if str(_HERE) not in _sys.path:
    _sys.path.insert(0, str(_HERE))
_EVOLUTION = _HERE.parents[1]
if str(_EVOLUTION) not in _sys.path:
    _sys.path.insert(0, str(_EVOLUTION))

from gearbox_controller import GearboxGuardError
from gearbox_controller_v2 import strict_bool
from gearbox_v2_1_repair_shadow_v01 import (
    MISSION_ID,
    RepairDecision,
    canonical_control_state,
    canonical_sha256,
    canonical_event_id,
    select_gear_repair_shadow,
)

AUTHORITY_ROLES = {"LCR-A"}
AUTHORITY_SCHEMA = "1.0-shadow"
AUTHORITY_GUARDS = {"HOLD", "ROLLBACK", "HUMAN_GATE", "BRAKE", "CLEAR"}
AUTHORITY_VERIFICATION_GATES = {"C_VERIFIED", "NOT_PROMOTION_EVIDENCE"}

# Fresh-read authority anchor for this shadow tranche. This is intentionally not a
# caller parameter. If formal authority advances, W02 must checkpoint/rebase this
# candidate before it can project any new authority decision.
PINNED_MISSION_STATE_BLOB_SHA = "e32e01fa304a857f5185951443682ea937335473"
PINNED_STEP_ID = 9


@dataclass(frozen=True)
class AuthorityDecisionEnvelope:
    schema_version: str
    mission_id: str
    step_id: int
    authority_role: str
    mission_state_blob_sha: str
    decision_id: str
    selected_state: str
    guard_status: str
    return_condition: str
    checkpoint_required: bool
    receiver_ack_required: bool
    verification_gate: str
    formal_mutation_allowed: bool = False

    @classmethod
    def from_value(cls, value: Any) -> "AuthorityDecisionEnvelope":
        if isinstance(value, cls):
            envelope = value
        elif isinstance(value, Mapping):
            try:
                envelope = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise GearboxGuardError("malformed AuthorityDecisionEnvelope") from exc
        else:
            raise GearboxGuardError("AuthorityDecisionEnvelope required")

        if envelope.schema_version != AUTHORITY_SCHEMA:
            raise GearboxGuardError("unsupported AuthorityDecisionEnvelope schema")
        if envelope.mission_id != MISSION_ID:
            raise GearboxGuardError("authority mission mismatch")
        if isinstance(envelope.step_id, bool) or not isinstance(envelope.step_id, int):
            raise GearboxGuardError("authority step_id must be integer")
        if envelope.step_id != PINNED_STEP_ID:
            raise GearboxGuardError("authority step mismatch; shadow rebase required")
        if envelope.authority_role not in AUTHORITY_ROLES:
            raise GearboxGuardError("untrusted authority role")

        actual_sha = canonical_sha256(envelope.mission_state_blob_sha, name="authority mission_state_blob_sha")
        if actual_sha != PINNED_MISSION_STATE_BLOB_SHA:
            raise GearboxGuardError("stale or cross-snapshot authority envelope; shadow rebase required")

        selected_state = canonical_control_state(envelope.selected_state)
        decision_id = canonical_event_id(envelope.decision_id)
        if type(envelope.guard_status) is not str:
            raise GearboxGuardError("authority guard_status must be explicit string")
        guard = envelope.guard_status.strip().upper()
        if guard not in AUTHORITY_GUARDS:
            raise GearboxGuardError("invalid authority guard_status")
        if selected_state == "R" and guard != "ROLLBACK":
            raise GearboxGuardError("R authority decision requires ROLLBACK guard")
        if selected_state == "N" and guard != "HOLD":
            raise GearboxGuardError("N authority decision requires HOLD guard")
        if type(envelope.return_condition) is not str or not envelope.return_condition.strip():
            raise GearboxGuardError("authority return_condition required")
        checkpoint = strict_bool(envelope.checkpoint_required, "authority checkpoint_required")
        receiver_ack = strict_bool(envelope.receiver_ack_required, "authority receiver_ack_required")
        formal_mutation = strict_bool(envelope.formal_mutation_allowed, "authority formal_mutation_allowed")
        if formal_mutation:
            raise GearboxGuardError("shadow authority envelope cannot authorize formal mutation")
        if type(envelope.verification_gate) is not str:
            raise GearboxGuardError("authority verification_gate must be explicit string")
        verification_gate = envelope.verification_gate.strip().upper()
        if verification_gate not in AUTHORITY_VERIFICATION_GATES:
            raise GearboxGuardError("invalid authority verification_gate")

        return cls(
            schema_version=AUTHORITY_SCHEMA,
            mission_id=MISSION_ID,
            step_id=PINNED_STEP_ID,
            authority_role=envelope.authority_role,
            mission_state_blob_sha=actual_sha,
            decision_id=decision_id,
            selected_state=selected_state,
            guard_status=guard,
            return_condition=envelope.return_condition.strip(),
            checkpoint_required=checkpoint,
            receiver_ack_required=receiver_ack,
            verification_gate=verification_gate,
            formal_mutation_allowed=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _project_authority(envelope: AuthorityDecisionEnvelope) -> RepairDecision:
    return RepairDecision(
        selected_state=envelope.selected_state,
        inherited_v2_gear=None,
        mode="FRESH_AUTHORITY_PROJECTION_SHADOW",
        reason=(
            f"exact pinned fresh authority decision {envelope.decision_id} projected from "
            f"{envelope.authority_role}; caller secretary/pressure/anti-thrash fallback has zero authority"
        ),
        terminal_policy_version="AUTHORITY_DECISION_ENVELOPE_V1_SHADOW",
        terminal_precedence_applied=envelope.selected_state in {"N", "R"},
        guard_status=envelope.guard_status,
        return_condition=envelope.return_condition,
        checkpoint_required=envelope.checkpoint_required,
        receiver_ack_required=envelope.receiver_ack_required,
        verification_gate=envelope.verification_gate,
        real_experience_claim_allowed=False,
        verified_experience_delta=0,
        operational_progress_delta=0,
        untrusted_secretary_routing_disabled=True,
        untrusted_shift_metrics_observational_only=True,
        credit_status="SHADOW_AUTHORITY_PROJECTION_ZERO_CREDIT",
        formal_mutation_allowed=False,
        repair_candidate_only=True,
    )


def select_gear_with_authority_projection_shadow(
    *,
    authority_conflict: bool = False,
    authority_decision_envelope: Any = None,
    **repair_kwargs: Any,
) -> RepairDecision:
    """Project exact pinned formal authority when an authority conflict exists.

    On conflict, permissive caller fallback is forbidden. A valid envelope bound to
    this tranche's fresh-read MISSION_STATE blob and step is mandatory. Missing,
    stale, cross-step, cross-role or malformed authority fails closed before ordinary
    secretary/pressure/anti-thrash telemetry is parsed.

    Without a conflict, the existing bounded repair shadow handles routing. An
    unsolicited authority envelope is ignored in this tranche rather than silently
    becoming a new authority path.
    """
    conflict = strict_bool(authority_conflict, "authority_conflict")
    if conflict:
        envelope = AuthorityDecisionEnvelope.from_value(authority_decision_envelope)
        return _project_authority(envelope)

    return select_gear_repair_shadow(
        authority_conflict=False,
        **repair_kwargs,
    )
