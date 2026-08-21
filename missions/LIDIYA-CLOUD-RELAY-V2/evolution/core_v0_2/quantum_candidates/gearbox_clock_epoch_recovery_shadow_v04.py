from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Mapping

from gearbox_controller import GearboxGuardError
from gearbox_authority_experience_signer_shadow_v01 import verify_signed_authority
from gearbox_external_monotonic_provider_shadow_v01 import (
    ExternalMonotonicProvider,
    MonotonicReceipt,
    ProviderBinding,
    require_external_binding,
    verify_monotonic_receipt,
)
from gearbox_secretary_runtime_freshness_shadow_v02 import verify_clock_checkpoint
from gearbox_secretary_signal_shadow_v01 import NEUTRAL_PRESSURE
from gearbox_authority_projection_shadow_v01 import PINNED_MISSION_STATE_BLOB_SHA

SCHEMA = "0.4-shadow"
MISSION_ID = "LCR-EVOLUTION-0005"
STEP_ID = 9
RECOVERY_STATE = "CLOCK_RECOVERY_REQUIRED"
READY_STATE = "CLOCK_EPOCH_READY_FOR_FRESH_AUTHORITY"
REENTERED_STATE = "CLOCK_EPOCH_REENTERED_SHADOW"


class ClockEpochRecoveryGuardError(GearboxGuardError):
    pass


def _canon_hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _token(value: Any, *, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value.strip()) > 128:
        raise ClockEpochRecoveryGuardError(f"{name} must be explicit bounded token")
    return value.strip()


def _require_mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ClockEpochRecoveryGuardError(f"{name} must be mapping")
    return value


def derive_clock_key_epoch_binding(
    *,
    clock_secret: bytes,
    clock_key_epoch: str,
    checkpoint_fingerprint: str,
    installation_id: str,
    runtime_id: str,
) -> str:
    """Bind a security-relevant clock-key epoch label to authenticated clock material.

    Shadow/test semantics only; this does not claim HSM/TPM protection.
    """
    if not isinstance(clock_secret, (bytes, bytearray)) or not clock_secret:
        raise ClockEpochRecoveryGuardError("clock_secret must be non-empty bytes")
    payload = {
        "schema_version": SCHEMA,
        "mission_id": MISSION_ID,
        "step_id": STEP_ID,
        "clock_key_epoch": _token(clock_key_epoch, name="clock_key_epoch"),
        "checkpoint_fingerprint": _token(checkpoint_fingerprint, name="checkpoint_fingerprint"),
        "installation_id": _token(installation_id, name="installation_id"),
        "runtime_id": _token(runtime_id, name="runtime_id"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(bytes(clock_secret), raw, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ClockEpochRoot:
    epoch_id: str
    clock_key_epoch: str
    clock_key_epoch_binding: str
    trust_snapshot_id: str
    mission_state_blob_sha: str
    installation_id: str
    runtime_id: str
    checkpoint_fingerprint: str
    provider_receipt: MonotonicReceipt
    provider_binding: ProviderBinding
    schema_version: str = SCHEMA
    mission_id: str = MISSION_ID
    step_id: int = STEP_ID

    def root_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mission_id": self.mission_id,
            "step_id": self.step_id,
            "epoch_id": self.epoch_id,
            "clock_key_epoch": self.clock_key_epoch,
            "clock_key_epoch_binding": self.clock_key_epoch_binding,
            "trust_snapshot_id": self.trust_snapshot_id,
            "mission_state_blob_sha": self.mission_state_blob_sha,
            "installation_id": self.installation_id,
            "runtime_id": self.runtime_id,
            "checkpoint_fingerprint": self.checkpoint_fingerprint,
        }


@dataclass(frozen=True)
class ClockRecoveryProjection:
    state: str
    epoch_id: str | None
    secretary_level: str
    pressure_inputs: dict[str, float]
    stale_pressure_carryover: bool
    prior_terminal_hold_carryover: bool
    routing_authority_allowed: bool
    formal_mutation_allowed: bool
    verified_experience_delta: int
    operational_progress_delta: int
    appraisal_delta: int
    personality_delta: int
    trauma_or_relief_delta: int
    fresh_authority_required: bool
    reason: str


def unresolved_chain_break(reason: str) -> ClockRecoveryProjection:
    return ClockRecoveryProjection(
        state=RECOVERY_STATE,
        epoch_id=None,
        secretary_level="UNKNOWN",
        pressure_inputs=dict(NEUTRAL_PRESSURE),
        stale_pressure_carryover=False,
        prior_terminal_hold_carryover=False,
        routing_authority_allowed=False,
        formal_mutation_allowed=False,
        verified_experience_delta=0,
        operational_progress_delta=0,
        appraisal_delta=0,
        personality_delta=0,
        trauma_or_relief_delta=0,
        fresh_authority_required=True,
        reason=_token(reason, name="reason"),
    )


def establish_replacement_clock_epoch(
    *,
    provider: ExternalMonotonicProvider,
    provider_receipt: MonotonicReceipt,
    replacement_checkpoint: Any,
    clock_secret: bytes,
    installation_id: str,
    runtime_id: str,
    epoch_id: str,
    clock_key_epoch: str,
    trust_snapshot_id: str,
    previous_provider_sequence: int,
    previous_provider_receipt_hash: str,
    forbidden_local_durability_domain_id: str,
    mission_state_blob_sha: str,
) -> tuple[ClockEpochRoot, ClockRecoveryProjection]:
    if mission_state_blob_sha != PINNED_MISSION_STATE_BLOB_SHA:
        raise ClockEpochRecoveryGuardError("fresh MISSION authority mismatch; rebase required")

    epoch_id = _token(epoch_id, name="epoch_id")
    clock_key_epoch = _token(clock_key_epoch, name="clock_key_epoch")
    trust_snapshot_id = _token(trust_snapshot_id, name="trust_snapshot_id")
    installation_id = _token(installation_id, name="installation_id")
    runtime_id = _token(runtime_id, name="runtime_id")

    checkpoint = verify_clock_checkpoint(
        replacement_checkpoint,
        clock_secret=clock_secret,
        installation_id=installation_id,
        runtime_id=runtime_id,
    )
    checkpoint_fingerprint = _canon_hash(checkpoint.unsigned_binding())
    clock_key_epoch_binding = derive_clock_key_epoch_binding(
        clock_secret=clock_secret,
        clock_key_epoch=clock_key_epoch,
        checkpoint_fingerprint=checkpoint_fingerprint,
        installation_id=installation_id,
        runtime_id=runtime_id,
    )

    payload = {
        "schema_version": SCHEMA,
        "mission_id": MISSION_ID,
        "step_id": STEP_ID,
        "epoch_id": epoch_id,
        "clock_key_epoch": clock_key_epoch,
        "clock_key_epoch_binding": clock_key_epoch_binding,
        "trust_snapshot_id": trust_snapshot_id,
        "mission_state_blob_sha": mission_state_blob_sha,
        "installation_id": installation_id,
        "runtime_id": runtime_id,
        "checkpoint_fingerprint": checkpoint_fingerprint,
    }

    binding = require_external_binding(
        provider,
        installation_id=installation_id,
        runtime_id=runtime_id,
        forbidden_local_durability_domain_id=forbidden_local_durability_domain_id,
    )
    verify_monotonic_receipt(
        provider,
        provider_receipt,
        expected_binding=binding,
        expected_previous_sequence=previous_provider_sequence,
        expected_previous_receipt_hash=previous_provider_receipt_hash,
        expected_payload_hash=_canon_hash(payload),
    )

    root = ClockEpochRoot(
        epoch_id=epoch_id,
        clock_key_epoch=clock_key_epoch,
        clock_key_epoch_binding=clock_key_epoch_binding,
        trust_snapshot_id=trust_snapshot_id,
        mission_state_blob_sha=mission_state_blob_sha,
        installation_id=installation_id,
        runtime_id=runtime_id,
        checkpoint_fingerprint=checkpoint_fingerprint,
        provider_receipt=provider_receipt,
        provider_binding=binding,
    )
    projection = ClockRecoveryProjection(
        state=READY_STATE,
        epoch_id=epoch_id,
        secretary_level="UNKNOWN",
        pressure_inputs=dict(NEUTRAL_PRESSURE),
        stale_pressure_carryover=False,
        prior_terminal_hold_carryover=False,
        routing_authority_allowed=False,
        formal_mutation_allowed=False,
        verified_experience_delta=0,
        operational_progress_delta=0,
        appraisal_delta=0,
        personality_delta=0,
        trauma_or_relief_delta=0,
        fresh_authority_required=True,
        reason="replacement clock/key epoch authenticated; stale secretary history excluded",
    )
    return root, projection


def complete_authenticated_reentry(
    *,
    root: ClockEpochRoot,
    provider: ExternalMonotonicProvider,
    clock_secret: bytes,
    signed_authority: Any,
    signer_trust_snapshot: Any,
    mission_state_blob_sha: str,
) -> ClockRecoveryProjection:
    """Final V04 re-entry gate with fail-closed provenance revalidation."""
    if mission_state_blob_sha != PINNED_MISSION_STATE_BLOB_SHA or root.mission_state_blob_sha != mission_state_blob_sha:
        raise ClockEpochRecoveryGuardError("fresh MISSION authority precedence failed")

    try:
        current_binding = provider.binding()
        current_floor = provider.read_floor()
    except Exception as exc:
        raise ClockEpochRecoveryGuardError("external provider head unavailable at final re-entry") from exc

    if current_binding != root.provider_binding:
        raise ClockEpochRecoveryGuardError("external provider binding changed after clock epoch establishment")
    if current_floor != root.provider_receipt.sequence:
        raise ClockEpochRecoveryGuardError("external provider head advanced or rolled back; stale root rejected")
    if not provider.verify(root.provider_receipt):
        raise ClockEpochRecoveryGuardError("root provider receipt no longer verifies")
    if root.provider_receipt.payload_hash != _canon_hash(root.root_payload()):
        raise ClockEpochRecoveryGuardError("root/provider payload commitment mismatch")

    expected_clock_binding = derive_clock_key_epoch_binding(
        clock_secret=clock_secret,
        clock_key_epoch=root.clock_key_epoch,
        checkpoint_fingerprint=root.checkpoint_fingerprint,
        installation_id=root.installation_id,
        runtime_id=root.runtime_id,
    )
    if not hmac.compare_digest(root.clock_key_epoch_binding, expected_clock_binding):
        raise ClockEpochRecoveryGuardError("clock_key_epoch provenance binding mismatch")

    trust_mapping = _require_mapping(signer_trust_snapshot, name="signer_trust_snapshot")
    signed_mapping = _require_mapping(signed_authority, name="signed_authority")
    trust_snapshot_id = _token(trust_mapping.get("snapshot_id"), name="signer_trust_snapshot.snapshot_id")
    authority_trust_snapshot_id = _token(
        signed_mapping.get("trust_snapshot_id"),
        name="signed_authority.trust_snapshot_id",
    )
    if root.trust_snapshot_id != trust_snapshot_id:
        raise ClockEpochRecoveryGuardError("root signer trust snapshot mismatch")
    if authority_trust_snapshot_id != trust_snapshot_id:
        raise ClockEpochRecoveryGuardError("signed authority trust snapshot mismatch")

    envelope = verify_signed_authority(signed_authority, signer_trust_snapshot)
    if envelope.mission_state_blob_sha != mission_state_blob_sha:
        raise ClockEpochRecoveryGuardError("signed authority not bound to fresh MISSION snapshot")

    return ClockRecoveryProjection(
        state=REENTERED_STATE,
        epoch_id=root.epoch_id,
        secretary_level="UNKNOWN",
        pressure_inputs=dict(NEUTRAL_PRESSURE),
        stale_pressure_carryover=False,
        prior_terminal_hold_carryover=False,
        routing_authority_allowed=False,
        formal_mutation_allowed=False,
        verified_experience_delta=0,
        operational_progress_delta=0,
        appraisal_delta=0,
        personality_delta=0,
        trauma_or_relief_delta=0,
        fresh_authority_required=False,
        reason=f"fresh authority {envelope.decision_id} accepted after V04 provenance revalidation",
    )


def pressure_history_dataflow_exclusion() -> dict[str, Any]:
    return {
        "operational_inputs_only": [
            "secretary_level", "pressure_fields", "valid_through_seq", "signal_id",
            "clock_seq", "checkpoint_hash", "clock_key_epoch", "provider_id",
            "signature_verdict", "recovery_counter",
        ],
        "forbidden_direct_sinks": [
            "Experience", "Experience_recurrence", "threat", "loss", "attachment",
            "competence", "learned_preference", "exploration_propensity", "identity",
            "goal_continuity", "personality_candidate", "P_base", "trauma", "relief_reward",
        ],
        "fresh_neutral_state_resets_pressure_history": True,
        "independent_verified_experience_required_for_cognitive_interpretation": True,
        "verified_experience_delta": 0,
        "appraisal_delta": 0,
        "personality_delta": 0,
        "formal_mutation_allowed": False,
    }


def recovery_boundaries() -> dict[str, Any]:
    return {
        "formal_mutation_allowed": False,
        "live_routing_authority_allowed": False,
        "recovery_counts_as_experience": False,
        "signature_success_counts_as_experience": False,
        "provider_maintenance_counts_as_experience": False,
        "stale_secretary_pressure_carryover": False,
        "prior_terminal_hold_carryover": False,
        "synthetic_provider_or_key_is_production_proof": False,
        "final_reentry_revalidates_provider_head": True,
        "final_reentry_binds_signer_trust_snapshot": True,
        "clock_key_epoch_has_authenticated_binding": True,
    }
