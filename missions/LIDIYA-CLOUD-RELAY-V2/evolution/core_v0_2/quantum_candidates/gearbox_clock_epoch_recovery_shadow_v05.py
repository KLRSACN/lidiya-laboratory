from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gearbox_clock_epoch_recovery_shadow_v03 import ClockEpochRecoveryGuardError, ClockRecoveryProjection
from gearbox_clock_epoch_recovery_shadow_v04 import (
    ReentryTrustBinding, complete_authenticated_reentry,
    establish_replacement_clock_epoch,
)
from gearbox_external_monotonic_provider_shadow_v01 import (
    ExternalMonotonicProvider, MonotonicReceipt, require_external_binding,
    verify_monotonic_receipt,
)
from gearbox_secretary_runtime_freshness_shadow_v02 import verify_clock_checkpoint
from gearbox_authority_projection_shadow_v01 import PINNED_MISSION_STATE_BLOB_SHA
from gearbox_clock_epoch_recovery_shadow_v03 import _canon_hash

SCHEMA = "0.5-shadow"


@dataclass(frozen=True)
class RecoveryCognitiveState:
    """Explicit zero-learning state used only for counterfactual regression."""
    verified_experience_count: int = 0
    appraisal_state: str = "UNCHANGED"
    drive_state: str = "UNCHANGED"
    exploration_state: str = "UNCHANGED"
    preference_state: str = "UNCHANGED"
    personality_state: str = "UNCHANGED"
    p_base_state: str = "READ_ONLY_UNCHANGED"
    trauma_state: str = "UNCHANGED"
    relief_state: str = "UNCHANGED"


def _current_head(provider: ExternalMonotonicProvider, head_receipt: MonotonicReceipt | None,
                  *, installation_id: str, runtime_id: str,
                  forbidden_local_durability_domain_id: str):
    binding = require_external_binding(
        provider, installation_id=installation_id, runtime_id=runtime_id,
        forbidden_local_durability_domain_id=forbidden_local_durability_domain_id,
    )
    floor = provider.read_floor()
    if floor == 0:
        if head_receipt is not None:
            raise ClockEpochRecoveryGuardError("genesis provider head must not supply receipt")
        return binding, 0, "GENESIS"
    if head_receipt is None or head_receipt.sequence != floor:
        raise ClockEpochRecoveryGuardError("authenticated current provider head receipt required")
    verify_monotonic_receipt(
        provider, head_receipt, expected_binding=binding,
        expected_previous_sequence=head_receipt.sequence - 1,
        expected_previous_receipt_hash=head_receipt.previous_receipt_hash,
        expected_payload_hash=head_receipt.payload_hash,
    )
    if provider.read_floor() != head_receipt.sequence:
        raise ClockEpochRecoveryGuardError("provider head moved during re-establishment")
    return binding, head_receipt.sequence, head_receipt.receipt_hash


def reestablish_current_clock_epoch(
    *, provider: ExternalMonotonicProvider, current_head_receipt: MonotonicReceipt | None,
    replacement_checkpoint: Any, clock_secret: bytes, installation_id: str, runtime_id: str,
    epoch_id: str, clock_key_epoch: str, trust_snapshot_id: str,
    forbidden_local_durability_domain_id: str, mission_state_blob_sha: str,
):
    """Establish a fresh root from the authenticated *current* provider head.

    A stale root is never revived. Benign provider progress is handled by minting a new
    provider-attested root after a quiet/current head is observed. Head churn is
    operational-only and contributes no cognitive/personality state.
    """
    if mission_state_blob_sha != PINNED_MISSION_STATE_BLOB_SHA:
        raise ClockEpochRecoveryGuardError("fresh MISSION authority mismatch; rebase required")
    _, previous_sequence, previous_hash = _current_head(
        provider, current_head_receipt, installation_id=installation_id, runtime_id=runtime_id,
        forbidden_local_durability_domain_id=forbidden_local_durability_domain_id,
    )
    checkpoint = verify_clock_checkpoint(
        replacement_checkpoint, clock_secret=clock_secret,
        installation_id=installation_id, runtime_id=runtime_id,
    )
    payload = {
        "schema_version":"0.3-shadow", "mission_id":"LCR-EVOLUTION-0005", "step_id":9,
        "epoch_id":epoch_id, "clock_key_epoch":clock_key_epoch,
        "trust_snapshot_id":trust_snapshot_id,
        "mission_state_blob_sha":mission_state_blob_sha,
        "installation_id":installation_id, "runtime_id":runtime_id,
        "checkpoint_fingerprint":_canon_hash(checkpoint.unsigned_binding()),
    }
    receipt = provider.issue(
        expected_previous_sequence=previous_sequence,
        previous_receipt_hash=previous_hash,
        payload_hash=_canon_hash(payload),
    )
    if receipt.sequence != previous_sequence + 1 or provider.read_floor() != receipt.sequence:
        raise ClockEpochRecoveryGuardError("provider head moved while issuing fresh root")
    return establish_replacement_clock_epoch(
        provider=provider, provider_receipt=receipt, replacement_checkpoint=replacement_checkpoint,
        clock_secret=clock_secret, installation_id=installation_id, runtime_id=runtime_id,
        epoch_id=epoch_id, clock_key_epoch=clock_key_epoch, trust_snapshot_id=trust_snapshot_id,
        previous_provider_sequence=previous_sequence, previous_provider_receipt_hash=previous_hash,
        forbidden_local_durability_domain_id=forbidden_local_durability_domain_id,
        mission_state_blob_sha=mission_state_blob_sha,
    )


def moving_head_recovery_boundaries() -> dict[str, Any]:
    return {
        "stale_root_revived": False,
        "fresh_current_head_root_required": True,
        "provider_head_churn_counts_as_experience": False,
        "retry_or_backoff_counts_as_experience": False,
        "recovery_duration_counts_as_experience": False,
        "appraisal_delta": 0,
        "drive_delta": 0,
        "exploration_delta": 0,
        "preference_delta": 0,
        "personality_delta": 0,
        "p_base_mutation_allowed": False,
        "trauma_or_relief_delta": 0,
        "formal_mutation_allowed": False,
        "production_provider_liveness_proven": False,
    }
