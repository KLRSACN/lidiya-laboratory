from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from gearbox_authority_experience_signer_shadow_v01 import SignerTrustSnapshot, verify_signed_authority
from gearbox_clock_epoch_recovery_shadow_v03 import (
    ClockEpochRecoveryGuardError, ClockRecoveryProjection, REENTERED_STATE,
    establish_replacement_clock_epoch as _establish_v03,
)
from gearbox_external_monotonic_provider_shadow_v01 import (
    ExternalMonotonicProvider, require_external_binding, verify_monotonic_receipt,
)
from gearbox_secretary_signal_shadow_v01 import NEUTRAL_PRESSURE
from gearbox_authority_projection_shadow_v01 import PINNED_MISSION_STATE_BLOB_SHA

SCHEMA = "0.4-shadow"


@dataclass(frozen=True)
class ReentryTrustBinding:
    clock_key_epoch: str
    clock_key_fingerprint_sha256: str


def clock_key_fingerprint(clock_secret: bytes) -> str:
    if not isinstance(clock_secret, bytes) or len(clock_secret) < 16:
        raise ClockEpochRecoveryGuardError("clock secret must be explicit key material")
    return hashlib.sha256(b"LCR-CLOCK-KEY\x00" + clock_secret).hexdigest()


def establish_replacement_clock_epoch(*, clock_secret: bytes, **kwargs: Any):
    """V04 keeps V03 root format but returns an explicit typed key binding.

    The fingerprint is synthetic shadow provenance only; it is not proof of protected
    production key storage. Re-entry must receive and verify this binding.
    """
    root, projection = _establish_v03(clock_secret=clock_secret, **kwargs)
    binding = ReentryTrustBinding(
        clock_key_epoch=root.clock_key_epoch,
        clock_key_fingerprint_sha256=clock_key_fingerprint(clock_secret),
    )
    return root, binding, projection


def complete_authenticated_reentry(
    *, root: Any, key_binding: ReentryTrustBinding, clock_secret: bytes,
    provider: ExternalMonotonicProvider, forbidden_local_durability_domain_id: str,
    signed_authority: Any, signer_trust_snapshot: Any, mission_state_blob_sha: str,
) -> ClockRecoveryProjection:
    """Final re-entry gate revalidates current provider head, trust snapshot and key identity."""
    if mission_state_blob_sha != PINNED_MISSION_STATE_BLOB_SHA or root.mission_state_blob_sha != mission_state_blob_sha:
        raise ClockEpochRecoveryGuardError("fresh MISSION authority precedence failed")

    binding = require_external_binding(
        provider, installation_id=root.installation_id, runtime_id=root.runtime_id,
        forbidden_local_durability_domain_id=forbidden_local_durability_domain_id,
    )
    if binding != root.provider_binding:
        raise ClockEpochRecoveryGuardError("provider binding changed before re-entry")
    receipt = root.provider_receipt
    verify_monotonic_receipt(
        provider, receipt, expected_binding=binding,
        expected_previous_sequence=receipt.sequence - 1,
        expected_previous_receipt_hash=receipt.previous_receipt_hash,
        expected_payload_hash=receipt.payload_hash,
    )
    if provider.read_floor() != receipt.sequence:
        raise ClockEpochRecoveryGuardError("stale clock epoch root: provider head advanced")

    trust = SignerTrustSnapshot.verify(signer_trust_snapshot)
    if trust.snapshot_id != root.trust_snapshot_id:
        raise ClockEpochRecoveryGuardError("clock root signer trust snapshot mismatch")

    if key_binding.clock_key_epoch != root.clock_key_epoch:
        raise ClockEpochRecoveryGuardError("clock key epoch mismatch")
    if key_binding.clock_key_fingerprint_sha256 != clock_key_fingerprint(clock_secret):
        raise ClockEpochRecoveryGuardError("clock key fingerprint mismatch")

    envelope = verify_signed_authority(signed_authority, signer_trust_snapshot)
    if envelope.mission_state_blob_sha != mission_state_blob_sha:
        raise ClockEpochRecoveryGuardError("signed authority not bound to fresh MISSION snapshot")

    return ClockRecoveryProjection(
        state=REENTERED_STATE, epoch_id=root.epoch_id, secretary_level="UNKNOWN",
        pressure_inputs=dict(NEUTRAL_PRESSURE), stale_pressure_carryover=False,
        prior_terminal_hold_carryover=False, routing_authority_allowed=False,
        formal_mutation_allowed=False, verified_experience_delta=0,
        operational_progress_delta=0, appraisal_delta=0, personality_delta=0,
        trauma_or_relief_delta=0, fresh_authority_required=False,
        reason=f"fresh authority {envelope.decision_id} accepted after current-head trust-root revalidation",
    )


def v04_boundaries() -> dict[str, Any]:
    return {
        "formal_mutation_allowed": False,
        "live_routing_authority_allowed": False,
        "provider_head_revalidated_at_reentry": True,
        "signer_snapshot_bound_to_root": True,
        "clock_key_epoch_security_relevant": True,
        "clock_key_fingerprint_required": True,
        "synthetic_key_or_provider_is_production_proof": False,
        "reentry_counts_as_experience": False,
    }
