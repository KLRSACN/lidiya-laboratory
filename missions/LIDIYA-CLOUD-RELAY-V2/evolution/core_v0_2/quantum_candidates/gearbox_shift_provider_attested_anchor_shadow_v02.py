from __future__ import annotations

from pathlib import Path
from typing import Any

# v0.2 hardening wrapper: every provider-state mutation is serialized through the
# same provider lock. v0.1 remains implementation detail; callers should use v0.2.
# Non-formal shadow only; no MISSION_STATE mutation and no LCR-C PASS claim.

import gearbox_shift_provider_attested_anchor_shadow_v01 as _v01
from gearbox_shift_durability_anchor_shadow_v01 import exclusive_writer_lock

ProviderAttestationGuardError = _v01.ProviderAttestationGuardError
ProviderAnchorAttestation = _v01.ProviderAnchorAttestation
RecoveryAuditAttestation = _v01.RecoveryAuditAttestation
PROVIDER_AUTHORITY = _v01.PROVIDER_AUTHORITY
PROVIDER_STATE_SCHEMA = _v01.PROVIDER_STATE_SCHEMA
ATTEST_SCHEMA = _v01.ATTEST_SCHEMA
AUDIT_SCHEMA = _v01.AUDIT_SCHEMA

initialize_provider_state = _v01.initialize_provider_state
attest_current_anchor = _v01.attest_current_anchor
verify_provider_attested_anchor = _v01.verify_provider_attested_anchor
verify_recovery_audit_attested = _v01.verify_recovery_audit_attested


def reconcile_attestation_journal_from_provider_state(*, provider_state_path: Path,
                                                       attestation_journal_path: Path,
                                                       provider_lock_path: Path,
                                                       provider_secret: bytes,
                                                       installation_id: str,
                                                       runtime_id: str) -> str:
    """Serialize journal recovery with the same lock used for provider attestation."""
    with exclusive_writer_lock(provider_lock_path):
        return _v01.reconcile_attestation_journal_from_provider_state(
            provider_state_path=provider_state_path,
            attestation_journal_path=attestation_journal_path,
            provider_secret=provider_secret,
            installation_id=installation_id,
            runtime_id=runtime_id,
        )


def attest_recovery_audit(*, recovery_registry_path: Path,
                          provider_state_path: Path,
                          provider_lock_path: Path,
                          provider_secret: bytes,
                          installation_id: str,
                          runtime_id: str) -> RecoveryAuditAttestation:
    """Serialize recovery-audit attestation against anchor-attestation state updates."""
    with exclusive_writer_lock(provider_lock_path):
        return _v01.attest_recovery_audit(
            recovery_registry_path=recovery_registry_path,
            provider_state_path=provider_state_path,
            provider_secret=provider_secret,
            installation_id=installation_id,
            runtime_id=runtime_id,
        )


def provider_shadow_boundaries() -> dict[str, Any]:
    return {
        "formal_mutation_allowed": False,
        "live_routing_authority_allowed": False,
        "experience_delta": 0,
        "operational_progress_delta": 0,
        "production_external_provider_proven": False,
        "provider_state_physical_independence_proven": False,
        "provider_state_rollback_resistance_proven": False,
        "synthetic_hmac_semantics_only": True,
    }
