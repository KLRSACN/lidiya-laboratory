from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from gearbox_controller import GearboxGuardError
from gearbox_authority_experience_signer_shadow_v01 import SignerTrustSnapshot, verify_signed_authority
from gearbox_external_monotonic_provider_shadow_v01 import (
    ExternalMonotonicProvider,
    MonotonicReceipt,
    ProviderBinding,
    require_external_binding,
    verify_monotonic_receipt,
)

SCHEMA = "1.0-shadow"
MISSION_ID = "LCR-EVOLUTION-0005"
STEP_ID = 9
GENESIS = "GENESIS"
GIT_BLOB_RE = re.compile(r"^[0-9a-fA-F]{40}$")
ZERO_PRESSURE = {
    "context_load_ratio": 0.0,
    "tool_failure_ratio": 0.0,
    "stale_pointer_ratio": 0.0,
    "storage_pressure_ratio": 0.0,
    "durable_progress_age_ratio": 0.0,
}


class SignerEpochRecoveryGuardError(ValueError):
    pass


def _canon(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _git_blob(value: Any) -> str:
    if type(value) is not str or not GIT_BLOB_RE.fullmatch(value):
        raise SignerEpochRecoveryGuardError("fresh mission blob must be 40-hex git sha")
    return value.lower()


def _trust(value: Any) -> SignerTrustSnapshot:
    try:
        return SignerTrustSnapshot.verify(value)
    except GearboxGuardError as exc:
        raise SignerEpochRecoveryGuardError(str(exc)) from exc


def _receipt(value: Any) -> MonotonicReceipt:
    if isinstance(value, MonotonicReceipt):
        return value
    if not isinstance(value, Mapping):
        raise SignerEpochRecoveryGuardError("provider receipt required")
    try:
        return MonotonicReceipt(**dict(value))
    except TypeError as exc:
        raise SignerEpochRecoveryGuardError("malformed provider receipt") from exc


@dataclass(frozen=True)
class TrustRootState:
    trust_snapshot: Mapping[str, Any]
    snapshot_sha256: str
    provider_payload_hash: str
    provider_receipt: MonotonicReceipt
    installation_id: str
    runtime_id: str
    local_durability_domain_id: str
    state: str
    secretary_level: str = "UNKNOWN"
    stale_pressure_carryover_allowed: bool = False
    terminal_hold_carryover_allowed: bool = False
    live_routing_authority_allowed: bool = False
    formal_mutation_allowed: bool = False
    experience_delta: int = 0
    operational_progress_delta: int = 0


def _binding(provider: ExternalMonotonicProvider, *, installation_id: str, runtime_id: str,
             local_domain: str) -> ProviderBinding:
    try:
        return require_external_binding(
            provider,
            installation_id=installation_id,
            runtime_id=runtime_id,
            forbidden_local_durability_domain_id=local_domain,
        )
    except ValueError as exc:
        raise SignerEpochRecoveryGuardError(str(exc)) from exc


def _verify_root(state: TrustRootState, provider: ExternalMonotonicProvider) -> SignerTrustSnapshot:
    trust = _trust(state.trust_snapshot)
    if _hash(dict(state.trust_snapshot)) != state.snapshot_sha256:
        raise SignerEpochRecoveryGuardError("TRUST_SNAPSHOT_HASH_MISMATCH")
    binding = _binding(
        provider,
        installation_id=state.installation_id,
        runtime_id=state.runtime_id,
        local_domain=state.local_durability_domain_id,
    )
    receipt = _receipt(state.provider_receipt)
    if provider.read_floor() != receipt.sequence:
        raise SignerEpochRecoveryGuardError("TRUST_ROOT_ROLLBACK_OR_FLOOR_DIVERGENCE")
    try:
        verify_monotonic_receipt(
            provider, receipt,
            expected_binding=binding,
            expected_previous_sequence=receipt.sequence - 1,
            expected_previous_receipt_hash=receipt.previous_receipt_hash,
            expected_payload_hash=state.provider_payload_hash,
        )
    except ValueError as exc:
        raise SignerEpochRecoveryGuardError(str(exc)) from exc
    return trust


def bootstrap_trust_root(*, trust_snapshot: Any, provider: ExternalMonotonicProvider,
                         installation_id: str, runtime_id: str,
                         local_durability_domain_id: str) -> TrustRootState:
    trust = _trust(trust_snapshot)
    binding = _binding(provider, installation_id=installation_id, runtime_id=runtime_id,
                       local_domain=local_durability_domain_id)
    if provider.read_floor() != 0:
        raise SignerEpochRecoveryGuardError("BOOTSTRAP_REQUIRES_EMPTY_PROVIDER_FLOOR")
    snapshot = dict(trust_snapshot)
    snapshot_sha = _hash(snapshot)
    payload_hash = _hash({
        "schema_version": SCHEMA,
        "purpose": "SIGNER_TRUST_ROOT_BOOTSTRAP",
        "mission_id": MISSION_ID,
        "step_id": STEP_ID,
        "snapshot_id": trust.snapshot_id,
        "snapshot_sha256": snapshot_sha,
    })
    receipt = provider.issue(expected_previous_sequence=0, previous_receipt_hash=GENESIS,
                             payload_hash=payload_hash)
    verify_monotonic_receipt(provider, receipt, expected_binding=binding,
                             expected_previous_sequence=0, expected_previous_receipt_hash=GENESIS,
                             expected_payload_hash=payload_hash)
    return TrustRootState(snapshot, snapshot_sha, payload_hash, receipt,
                          installation_id, runtime_id, local_durability_domain_id,
                          "ACTIVE_TRUST_ROOT_SHADOW")


def recover_new_epoch(*, current_root: TrustRootState, replacement_trust_snapshot: Any,
                      provider: ExternalMonotonicProvider,
                      fresh_mission_state_blob_sha: str) -> TrustRootState:
    current = _verify_root(current_root, provider)
    replacement = _trust(replacement_trust_snapshot)
    fresh_blob = _git_blob(fresh_mission_state_blob_sha)
    replacement_map = dict(replacement_trust_snapshot)
    replacement_sha = _hash(replacement_map)

    if replacement.previous_snapshot_sha256.lower() != current_root.snapshot_sha256.lower():
        raise SignerEpochRecoveryGuardError("REPLACEMENT_PREDECESSOR_MISMATCH")
    if replacement.snapshot_id == current.snapshot_id:
        raise SignerEpochRecoveryGuardError("SNAPSHOT_ID_DID_NOT_ADVANCE")
    if replacement.authority_active_epoch == current.authority_active_epoch:
        raise SignerEpochRecoveryGuardError("AUTHORITY_EPOCH_DID_NOT_ROTATE")
    if current.authority_active_epoch not in replacement.revoked_epochs:
        raise SignerEpochRecoveryGuardError("OLD_AUTHORITY_EPOCH_NOT_REVOKED")
    for role, old_epoch in current.verifier_active_epochs.items():
        new_epoch = replacement.verifier_active_epochs.get(role)
        if new_epoch is None or new_epoch == old_epoch:
            raise SignerEpochRecoveryGuardError("VERIFIER_EPOCH_DID_NOT_ROTATE")
        if old_epoch not in replacement.revoked_epochs:
            raise SignerEpochRecoveryGuardError("OLD_VERIFIER_EPOCH_NOT_REVOKED")

    payload_hash = _hash({
        "schema_version": SCHEMA,
        "purpose": "AUTHENTICATED_NEW_EPOCH_RECOVERY",
        "mission_id": MISSION_ID,
        "step_id": STEP_ID,
        "previous_snapshot_sha256": current_root.snapshot_sha256,
        "replacement_snapshot_sha256": replacement_sha,
        "fresh_mission_state_blob_sha": fresh_blob,
        "stale_pressure_carryover_allowed": False,
        "terminal_hold_carryover_allowed": False,
        "recovery_counts_as_experience": False,
    })
    previous = _receipt(current_root.provider_receipt)
    binding = _binding(provider, installation_id=current_root.installation_id,
                       runtime_id=current_root.runtime_id,
                       local_domain=current_root.local_durability_domain_id)
    receipt = provider.issue(expected_previous_sequence=previous.sequence,
                             previous_receipt_hash=previous.receipt_hash,
                             payload_hash=payload_hash)
    verify_monotonic_receipt(provider, receipt, expected_binding=binding,
                             expected_previous_sequence=previous.sequence,
                             expected_previous_receipt_hash=previous.receipt_hash,
                             expected_payload_hash=payload_hash)
    return TrustRootState(
        replacement_map, replacement_sha, payload_hash, receipt,
        current_root.installation_id, current_root.runtime_id,
        current_root.local_durability_domain_id,
        "AUTHENTICATED_NEW_EPOCH_RECOVERED_AWAITING_FRESH_AUTHORITY",
        secretary_level="UNKNOWN",
        stale_pressure_carryover_allowed=False,
        terminal_hold_carryover_allowed=False,
        live_routing_authority_allowed=False,
        formal_mutation_allowed=False,
        experience_delta=0,
        operational_progress_delta=0,
    )


@dataclass(frozen=True)
class ShadowReentry:
    state: str
    selected_state: str
    guard_status: str
    return_condition: str
    secretary_level: str
    pressure_inputs: Mapping[str, float]
    stale_pressure_carryover_allowed: bool = False
    terminal_hold_carryover_allowed: bool = False
    live_routing_authority_allowed: bool = False
    formal_mutation_allowed: bool = False
    experience_delta: int = 0
    operational_progress_delta: int = 0


def complete_shadow_reentry(*, recovered_root: TrustRootState,
                            provider: ExternalMonotonicProvider,
                            signed_authority: Any) -> ShadowReentry:
    _verify_root(recovered_root, provider)
    if recovered_root.state != "AUTHENTICATED_NEW_EPOCH_RECOVERED_AWAITING_FRESH_AUTHORITY":
        raise SignerEpochRecoveryGuardError("ROOT_NOT_READY_FOR_REENTRY")
    try:
        authority = verify_signed_authority(signed_authority, recovered_root.trust_snapshot)
    except GearboxGuardError as exc:
        raise SignerEpochRecoveryGuardError(str(exc)) from exc
    return ShadowReentry(
        state="SHADOW_REENTRY_FRESH_AUTHORITY_READY",
        selected_state=authority.selected_state,
        guard_status=authority.guard_status,
        return_condition=authority.return_condition,
        secretary_level="UNKNOWN",
        pressure_inputs=dict(ZERO_PRESSURE),
    )


def recovery_boundaries() -> dict[str, object]:
    return {
        "formal_mutation_allowed": False,
        "live_routing_authority_allowed": False,
        "recovery_counts_as_experience": False,
        "recovery_counts_as_operational_progress": False,
        "stale_pressure_carryover_allowed": False,
        "terminal_hold_carryover_allowed": False,
        "real_external_provider_installed": False,
        "production_signer_protection_proven": False,
    }
