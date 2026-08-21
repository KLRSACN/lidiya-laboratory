from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Non-formal shadow interface only. This module defines the trust boundary that a
# real TPM/HSM/remote monotonic service would have to satisfy. It does not claim
# that any such provider is installed or verified.

class ExternalProviderGuardError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderBinding:
    provider_id: str
    durability_domain_id: str
    installation_id: str
    runtime_id: str


@dataclass(frozen=True)
class MonotonicReceipt:
    provider_id: str
    durability_domain_id: str
    installation_id: str
    runtime_id: str
    sequence: int
    previous_receipt_hash: str
    payload_hash: str
    receipt_hash: str
    signature: str


@runtime_checkable
class ExternalMonotonicProvider(Protocol):
    """Minimum adapter contract for an actually external monotonic trust root."""

    def binding(self) -> ProviderBinding: ...
    def read_floor(self) -> int: ...
    def issue(self, *, expected_previous_sequence: int, previous_receipt_hash: str,
              payload_hash: str) -> MonotonicReceipt: ...
    def verify(self, receipt: MonotonicReceipt) -> bool: ...


def require_external_binding(provider: ExternalMonotonicProvider, *,
                             installation_id: str, runtime_id: str,
                             forbidden_local_durability_domain_id: str) -> ProviderBinding:
    if not isinstance(provider, ExternalMonotonicProvider):
        raise ExternalProviderGuardError("PROVIDER_ADAPTER_PROTOCOL_MISMATCH")
    binding = provider.binding()
    if not binding.provider_id or not binding.durability_domain_id:
        raise ExternalProviderGuardError("PROVIDER_BINDING_INCOMPLETE")
    if binding.installation_id != installation_id or binding.runtime_id != runtime_id:
        raise ExternalProviderGuardError("PROVIDER_SCOPE_MISMATCH")
    if binding.durability_domain_id == forbidden_local_durability_domain_id:
        raise ExternalProviderGuardError("PROVIDER_NOT_EXTERNAL_TO_CONSUMER_DURABILITY_DOMAIN")
    return binding


def verify_monotonic_receipt(provider: ExternalMonotonicProvider, receipt: MonotonicReceipt,
                             *, expected_binding: ProviderBinding,
                             expected_previous_sequence: int,
                             expected_previous_receipt_hash: str,
                             expected_payload_hash: str) -> None:
    if receipt.provider_id != expected_binding.provider_id:
        raise ExternalProviderGuardError("PROVIDER_ID_MISMATCH")
    if receipt.durability_domain_id != expected_binding.durability_domain_id:
        raise ExternalProviderGuardError("DURABILITY_DOMAIN_MISMATCH")
    if receipt.installation_id != expected_binding.installation_id or receipt.runtime_id != expected_binding.runtime_id:
        raise ExternalProviderGuardError("RECEIPT_SCOPE_MISMATCH")
    if receipt.sequence != expected_previous_sequence + 1:
        raise ExternalProviderGuardError("NON_CONTIGUOUS_PROVIDER_SEQUENCE")
    if receipt.previous_receipt_hash != expected_previous_receipt_hash:
        raise ExternalProviderGuardError("PROVIDER_RECEIPT_CHAIN_MISMATCH")
    if receipt.payload_hash != expected_payload_hash:
        raise ExternalProviderGuardError("PROVIDER_PAYLOAD_MISMATCH")
    if not provider.verify(receipt):
        raise ExternalProviderGuardError("PROVIDER_SIGNATURE_INVALID")
    floor = provider.read_floor()
    if floor < receipt.sequence:
        raise ExternalProviderGuardError("PROVIDER_MONOTONIC_FLOOR_BEHIND_RECEIPT")


def provider_adapter_boundaries() -> dict[str, object]:
    return {
        "formal_mutation_allowed": False,
        "live_routing_authority_allowed": False,
        "experience_delta": 0,
        "operational_progress_delta": 0,
        "external_provider_interface_defined": True,
        "real_external_provider_installed": False,
        "hsm_tpm_remote_service_proven": False,
        "consumer_and_provider_common_rollback_detectable_only_if_domains_are_independent": True,
    }
