from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

# Non-formal shadow research only. This module models an external provider boundary
# using synthetic HMAC test material. It does not establish a production HSM/TPM,
# does not mutate MISSION_STATE, and does not claim LCR-C verification.

from gearbox_shift_durability_anchor_shadow_v01 import (
    ZERO_HASH,
    _atomic_save,
    _load_anchor,
    exclusive_writer_lock,
    verify_anchor,
)
from gearbox_shift_anchor_trust_recovery_shadow_v01 import (
    PROVIDER_DOMAIN_ID,
    PROVIDER_ID,
    PROVIDER_KEY_ID,
    _validate_provider_secret,
)
from gearbox_shift_history_shadow_v01 import MISSION_ID, STEP_ID

ATTEST_SCHEMA = "0.1-shadow"
PROVIDER_STATE_SCHEMA = "0.1-shadow"
ATTEST_JOURNAL_SCHEMA = "0.1-shadow"
AUDIT_SCHEMA = "0.1-shadow"
PROVIDER_AUTHORITY = "SYNTHETIC_EXTERNAL_PROVIDER_SHADOW"


class ProviderAttestationGuardError(ValueError):
    pass


def _explicit_string(value: Any, *, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ProviderAttestationGuardError(f"{name} must be explicit non-empty string")
    return value.strip()


def _nonnegative_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderAttestationGuardError(f"{name} must be nonnegative integer")
    return value


def _sha256(value: Any, *, name: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise ProviderAttestationGuardError(f"{name} must be 64-hex sha256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProviderAttestationGuardError(f"{name} must be 64-hex sha256") from exc
    return value.lower()


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_mapping(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _mac(payload: Mapping[str, Any], secret: bytes) -> str:
    return hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderAttestationGuardError(f"{label} unreadable") from exc
    if not isinstance(data, dict):
        raise ProviderAttestationGuardError(f"{label} must be object")
    return data


def _canonical_file_hash(path: Path, *, label: str) -> str:
    data = _read_object(path, label=label)
    return _hash_mapping(data)


@dataclass(frozen=True)
class ProviderAnchorAttestation:
    provider_seq: int
    anchor_hash: str
    anchor_seq: int
    ledger_head_hash: str
    previous_attestation_hash: str
    installation_id: str
    runtime_id: str
    mac_sha256: str
    provider_id: str = PROVIDER_ID
    provider_key_id: str = PROVIDER_KEY_ID
    durability_domain_id: str = PROVIDER_DOMAIN_ID
    authority_id: str = PROVIDER_AUTHORITY
    mission_id: str = MISSION_ID
    step_id: int = STEP_ID
    schema_version: str = ATTEST_SCHEMA

    def unsigned_binding(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("mac_sha256")
        return data

    def attestation_hash(self) -> str:
        return _hash_mapping(asdict(self))

    @classmethod
    def from_value(cls, value: Any) -> "ProviderAnchorAttestation":
        if isinstance(value, cls):
            raw = value
        elif isinstance(value, Mapping):
            try:
                raw = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise ProviderAttestationGuardError("malformed provider anchor attestation") from exc
        else:
            raise ProviderAttestationGuardError("provider anchor attestation must be mapping or receipt")
        seq = _nonnegative_int(raw.provider_seq, name="provider_seq")
        anchor_seq = _nonnegative_int(raw.anchor_seq, name="anchor_seq")
        anchor_hash = _sha256(raw.anchor_hash, name="anchor_hash")
        ledger_head = _sha256(raw.ledger_head_hash, name="ledger_head_hash")
        previous = _sha256(raw.previous_attestation_hash, name="previous_attestation_hash")
        mac = _sha256(raw.mac_sha256, name="mac_sha256")
        installation_id = _explicit_string(raw.installation_id, name="installation_id")
        runtime_id = _explicit_string(raw.runtime_id, name="runtime_id")
        if raw.provider_id != PROVIDER_ID or raw.provider_key_id != PROVIDER_KEY_ID:
            raise ProviderAttestationGuardError("provider identity mismatch")
        if raw.durability_domain_id != PROVIDER_DOMAIN_ID or raw.authority_id != PROVIDER_AUTHORITY:
            raise ProviderAttestationGuardError("provider authority/domain mismatch")
        if raw.mission_id != MISSION_ID or raw.step_id != STEP_ID or raw.schema_version != ATTEST_SCHEMA:
            raise ProviderAttestationGuardError("provider attestation scope/schema mismatch")
        return cls(seq, anchor_hash, anchor_seq, ledger_head, previous, installation_id, runtime_id, mac)


@dataclass(frozen=True)
class RecoveryAuditAttestation:
    audit_seq: int
    recovery_registry_sha256: str
    anchor_attestation_hash: str
    previous_audit_hash: str
    installation_id: str
    runtime_id: str
    mac_sha256: str
    provider_id: str = PROVIDER_ID
    provider_key_id: str = PROVIDER_KEY_ID
    durability_domain_id: str = PROVIDER_DOMAIN_ID
    authority_id: str = PROVIDER_AUTHORITY
    mission_id: str = MISSION_ID
    step_id: int = STEP_ID
    schema_version: str = AUDIT_SCHEMA

    def unsigned_binding(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("mac_sha256")
        return data

    def audit_hash(self) -> str:
        return _hash_mapping(asdict(self))

    @classmethod
    def from_value(cls, value: Any) -> "RecoveryAuditAttestation":
        if isinstance(value, cls):
            raw = value
        elif isinstance(value, Mapping):
            try:
                raw = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise ProviderAttestationGuardError("malformed recovery audit attestation") from exc
        else:
            raise ProviderAttestationGuardError("recovery audit attestation must be mapping or receipt")
        audit_seq = _nonnegative_int(raw.audit_seq, name="audit_seq")
        registry_hash = _sha256(raw.recovery_registry_sha256, name="recovery_registry_sha256")
        anchor_hash = _sha256(raw.anchor_attestation_hash, name="anchor_attestation_hash")
        previous = _sha256(raw.previous_audit_hash, name="previous_audit_hash")
        mac = _sha256(raw.mac_sha256, name="mac_sha256")
        installation_id = _explicit_string(raw.installation_id, name="installation_id")
        runtime_id = _explicit_string(raw.runtime_id, name="runtime_id")
        if raw.provider_id != PROVIDER_ID or raw.provider_key_id != PROVIDER_KEY_ID:
            raise ProviderAttestationGuardError("audit provider identity mismatch")
        if raw.durability_domain_id != PROVIDER_DOMAIN_ID or raw.authority_id != PROVIDER_AUTHORITY:
            raise ProviderAttestationGuardError("audit provider authority/domain mismatch")
        if raw.mission_id != MISSION_ID or raw.step_id != STEP_ID or raw.schema_version != AUDIT_SCHEMA:
            raise ProviderAttestationGuardError("audit attestation scope/schema mismatch")
        return cls(audit_seq, registry_hash, anchor_hash, previous, installation_id, runtime_id, mac)


def _verify_anchor_attestation(value: Any, *, provider_secret: bytes) -> ProviderAnchorAttestation:
    secret = _validate_provider_secret(provider_secret)
    receipt = ProviderAnchorAttestation.from_value(value)
    expected = _mac(receipt.unsigned_binding(), secret)
    if not hmac.compare_digest(expected, receipt.mac_sha256):
        raise ProviderAttestationGuardError("provider anchor attestation authentication failed")
    return receipt


def _verify_audit_attestation(value: Any, *, provider_secret: bytes) -> RecoveryAuditAttestation:
    secret = _validate_provider_secret(provider_secret)
    receipt = RecoveryAuditAttestation.from_value(value)
    expected = _mac(receipt.unsigned_binding(), secret)
    if not hmac.compare_digest(expected, receipt.mac_sha256):
        raise ProviderAttestationGuardError("recovery audit attestation authentication failed")
    return receipt


def _state_unsigned(state: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(state)
    data.pop("mac_sha256", None)
    return data


def _save_provider_state(path: Path, state: Mapping[str, Any], *, provider_secret: bytes) -> None:
    secret = _validate_provider_secret(provider_secret)
    payload = dict(state)
    payload["mac_sha256"] = _mac(_state_unsigned(payload), secret)
    _atomic_save(path, payload)


def _load_provider_state(path: Path, *, provider_secret: bytes,
                         installation_id: str, runtime_id: str) -> dict[str, Any]:
    secret = _validate_provider_secret(provider_secret)
    data = _read_object(path, label="provider state")
    if data.get("schema_version") != PROVIDER_STATE_SCHEMA:
        raise ProviderAttestationGuardError("provider state schema mismatch")
    if data.get("provider_id") != PROVIDER_ID or data.get("provider_key_id") != PROVIDER_KEY_ID:
        raise ProviderAttestationGuardError("provider state identity mismatch")
    if data.get("durability_domain_id") != PROVIDER_DOMAIN_ID:
        raise ProviderAttestationGuardError("provider state domain mismatch")
    if data.get("mission_id") != MISSION_ID or data.get("step_id") != STEP_ID:
        raise ProviderAttestationGuardError("provider state mission/step mismatch")
    if data.get("installation_id") != installation_id or data.get("runtime_id") != runtime_id:
        raise ProviderAttestationGuardError("provider state scope mismatch")
    expected = _mac(_state_unsigned(data), secret)
    if not hmac.compare_digest(expected, str(data.get("mac_sha256", ""))):
        raise ProviderAttestationGuardError("provider state authentication failed")
    _nonnegative_int(data.get("last_provider_seq"), name="last_provider_seq")
    _sha256(data.get("last_attestation_hash"), name="last_attestation_hash")
    _nonnegative_int(data.get("last_audit_seq"), name="last_audit_seq")
    _sha256(data.get("last_audit_hash"), name="last_audit_hash")
    return data


def initialize_provider_state(*, provider_state_path: Path, provider_secret: bytes,
                              installation_id: str, runtime_id: str) -> None:
    installation_id = _explicit_string(installation_id, name="installation_id")
    runtime_id = _explicit_string(runtime_id, name="runtime_id")
    if provider_state_path.exists():
        raise ProviderAttestationGuardError("provider state already exists")
    state = {
        "schema_version": PROVIDER_STATE_SCHEMA,
        "provider_id": PROVIDER_ID,
        "provider_key_id": PROVIDER_KEY_ID,
        "durability_domain_id": PROVIDER_DOMAIN_ID,
        "mission_id": MISSION_ID,
        "step_id": STEP_ID,
        "installation_id": installation_id,
        "runtime_id": runtime_id,
        "last_provider_seq": 0,
        "last_attestation_hash": ZERO_HASH,
        "latest_attestation": None,
        "last_audit_seq": 0,
        "last_audit_hash": ZERO_HASH,
        "latest_audit_attestation": None,
    }
    _save_provider_state(provider_state_path, state, provider_secret=provider_secret)


def _load_journal(path: Path, *, provider_secret: bytes,
                  installation_id: str, runtime_id: str) -> list[ProviderAnchorAttestation]:
    if not path.exists():
        return []
    data = _read_object(path, label="provider attestation journal")
    if data.get("schema_version") != ATTEST_JOURNAL_SCHEMA:
        raise ProviderAttestationGuardError("provider attestation journal schema mismatch")
    raw_receipts = data.get("receipts")
    if not isinstance(raw_receipts, list):
        raise ProviderAttestationGuardError("provider attestation journal malformed")
    receipts: list[ProviderAnchorAttestation] = []
    previous_hash = ZERO_HASH
    expected_seq = 1
    for raw in raw_receipts:
        receipt = _verify_anchor_attestation(raw, provider_secret=provider_secret)
        if receipt.installation_id != installation_id or receipt.runtime_id != runtime_id:
            raise ProviderAttestationGuardError("provider attestation journal scope mismatch")
        if receipt.provider_seq != expected_seq:
            raise ProviderAttestationGuardError("provider attestation sequence gap")
        if receipt.previous_attestation_hash != previous_hash:
            raise ProviderAttestationGuardError("provider attestation chain mismatch")
        receipts.append(receipt)
        previous_hash = receipt.attestation_hash()
        expected_seq += 1
    return receipts


def _save_journal(path: Path, receipts: list[ProviderAnchorAttestation]) -> None:
    _atomic_save(path, {
        "schema_version": ATTEST_JOURNAL_SCHEMA,
        "receipts": [asdict(item) for item in receipts],
    })


def attest_current_anchor(*, registry_path: Path, anchor_path: Path, provider_state_path: Path,
                          attestation_journal_path: Path, provider_lock_path: Path,
                          provider_secret: bytes, installation_id: str, runtime_id: str) -> ProviderAnchorAttestation:
    """Issue one provider-authenticated receipt for the exact current matched anchor.

    Provider state is written before the consumer journal. If a crash occurs in between,
    the provider state retains the exact latest signed receipt so the journal can be
    reconciled without inventing a new receipt or decrementing the provider sequence.
    """
    with exclusive_writer_lock(provider_lock_path):
        status = verify_anchor(
            registry_path=registry_path, anchor_path=anchor_path,
            installation_id=installation_id, runtime_id=runtime_id,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        )
        if status.status != "ANCHOR_MATCH":
            raise ProviderAttestationGuardError(f"cannot attest anchor from {status.status}")
        anchor = _load_anchor(
            anchor_path, installation_id=installation_id, runtime_id=runtime_id,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        )
        state = _load_provider_state(
            provider_state_path, provider_secret=provider_secret,
            installation_id=installation_id, runtime_id=runtime_id,
        )
        receipts = _load_journal(
            attestation_journal_path, provider_secret=provider_secret,
            installation_id=installation_id, runtime_id=runtime_id,
        )
        journal_hash = receipts[-1].attestation_hash() if receipts else ZERO_HASH
        journal_seq = receipts[-1].provider_seq if receipts else 0
        if journal_hash != state["last_attestation_hash"] or journal_seq != state["last_provider_seq"]:
            raise ProviderAttestationGuardError("PROVIDER_JOURNAL_STATE_DIVERGENCE")
        secret = _validate_provider_secret(provider_secret)
        unsigned = {
            "provider_seq": state["last_provider_seq"] + 1,
            "anchor_hash": anchor.anchor_hash(),
            "anchor_seq": anchor.anchor_seq,
            "ledger_head_hash": anchor.ledger_head_hash,
            "previous_attestation_hash": state["last_attestation_hash"],
            "installation_id": installation_id,
            "runtime_id": runtime_id,
            "provider_id": PROVIDER_ID,
            "provider_key_id": PROVIDER_KEY_ID,
            "durability_domain_id": PROVIDER_DOMAIN_ID,
            "authority_id": PROVIDER_AUTHORITY,
            "mission_id": MISSION_ID,
            "step_id": STEP_ID,
            "schema_version": ATTEST_SCHEMA,
        }
        receipt = ProviderAnchorAttestation.from_value({**unsigned, "mac_sha256": _mac(unsigned, secret)})
        next_state = dict(state)
        next_state["last_provider_seq"] = receipt.provider_seq
        next_state["last_attestation_hash"] = receipt.attestation_hash()
        next_state["latest_attestation"] = asdict(receipt)
        _save_provider_state(provider_state_path, next_state, provider_secret=provider_secret)
        receipts.append(receipt)
        _save_journal(attestation_journal_path, receipts)
        return receipt


def reconcile_attestation_journal_from_provider_state(*, provider_state_path: Path,
                                                       attestation_journal_path: Path,
                                                       provider_secret: bytes,
                                                       installation_id: str, runtime_id: str) -> str:
    """Recover exactly one provider-issued journal write lost after provider state commit."""
    state = _load_provider_state(
        provider_state_path, provider_secret=provider_secret,
        installation_id=installation_id, runtime_id=runtime_id,
    )
    receipts = _load_journal(
        attestation_journal_path, provider_secret=provider_secret,
        installation_id=installation_id, runtime_id=runtime_id,
    )
    journal_seq = receipts[-1].provider_seq if receipts else 0
    journal_hash = receipts[-1].attestation_hash() if receipts else ZERO_HASH
    if journal_seq == state["last_provider_seq"] and journal_hash == state["last_attestation_hash"]:
        return "JOURNAL_ALREADY_MATCHED_NO_OP"
    if state["last_provider_seq"] != journal_seq + 1:
        raise ProviderAttestationGuardError("provider journal divergence exceeds one recoverable receipt")
    latest_raw = state.get("latest_attestation")
    latest = _verify_anchor_attestation(latest_raw, provider_secret=provider_secret)
    if latest.provider_seq != state["last_provider_seq"]:
        raise ProviderAttestationGuardError("provider latest attestation sequence mismatch")
    if latest.previous_attestation_hash != journal_hash:
        raise ProviderAttestationGuardError("provider latest attestation predecessor mismatch")
    if latest.attestation_hash() != state["last_attestation_hash"]:
        raise ProviderAttestationGuardError("provider latest attestation hash mismatch")
    receipts.append(latest)
    _save_journal(attestation_journal_path, receipts)
    return "JOURNAL_RECONCILED_FROM_PROVIDER_STATE"


def verify_provider_attested_anchor(*, registry_path: Path, anchor_path: Path,
                                    provider_state_path: Path, attestation_journal_path: Path,
                                    provider_secret: bytes, installation_id: str, runtime_id: str) -> str:
    status = verify_anchor(
        registry_path=registry_path, anchor_path=anchor_path,
        installation_id=installation_id, runtime_id=runtime_id,
        durability_domain_id=PROVIDER_DOMAIN_ID,
    )
    if status.status != "ANCHOR_MATCH":
        raise ProviderAttestationGuardError(status.status)
    anchor = _load_anchor(
        anchor_path, installation_id=installation_id, runtime_id=runtime_id,
        durability_domain_id=PROVIDER_DOMAIN_ID,
    )
    state = _load_provider_state(
        provider_state_path, provider_secret=provider_secret,
        installation_id=installation_id, runtime_id=runtime_id,
    )
    receipts = _load_journal(
        attestation_journal_path, provider_secret=provider_secret,
        installation_id=installation_id, runtime_id=runtime_id,
    )
    if not receipts:
        raise ProviderAttestationGuardError("provider attestation missing")
    latest = receipts[-1]
    if latest.provider_seq != state["last_provider_seq"] or latest.attestation_hash() != state["last_attestation_hash"]:
        raise ProviderAttestationGuardError("PROVIDER_MONOTONIC_FLOOR_MISMATCH")
    if latest.anchor_hash != anchor.anchor_hash() or latest.anchor_seq != anchor.anchor_seq or latest.ledger_head_hash != anchor.ledger_head_hash:
        raise ProviderAttestationGuardError("provider attestation does not bind current anchor")
    return "PROVIDER_ATTESTED_ANCHOR_MATCH"


def attest_recovery_audit(*, recovery_registry_path: Path, provider_state_path: Path,
                          provider_secret: bytes, installation_id: str, runtime_id: str) -> RecoveryAuditAttestation:
    """Bind the exact current recovery-audit registry to the provider monotonic state."""
    state = _load_provider_state(
        provider_state_path, provider_secret=provider_secret,
        installation_id=installation_id, runtime_id=runtime_id,
    )
    latest_anchor_hash = state["last_attestation_hash"]
    if latest_anchor_hash == ZERO_HASH:
        raise ProviderAttestationGuardError("recovery audit requires at least one anchor attestation")
    registry_hash = _canonical_file_hash(recovery_registry_path, label="recovery registry")
    secret = _validate_provider_secret(provider_secret)
    unsigned = {
        "audit_seq": state["last_audit_seq"] + 1,
        "recovery_registry_sha256": registry_hash,
        "anchor_attestation_hash": latest_anchor_hash,
        "previous_audit_hash": state["last_audit_hash"],
        "installation_id": installation_id,
        "runtime_id": runtime_id,
        "provider_id": PROVIDER_ID,
        "provider_key_id": PROVIDER_KEY_ID,
        "durability_domain_id": PROVIDER_DOMAIN_ID,
        "authority_id": PROVIDER_AUTHORITY,
        "mission_id": MISSION_ID,
        "step_id": STEP_ID,
        "schema_version": AUDIT_SCHEMA,
    }
    receipt = RecoveryAuditAttestation.from_value({**unsigned, "mac_sha256": _mac(unsigned, secret)})
    next_state = dict(state)
    next_state["last_audit_seq"] = receipt.audit_seq
    next_state["last_audit_hash"] = receipt.audit_hash()
    next_state["latest_audit_attestation"] = asdict(receipt)
    _save_provider_state(provider_state_path, next_state, provider_secret=provider_secret)
    return receipt


def verify_recovery_audit_attested(*, recovery_registry_path: Path, provider_state_path: Path,
                                   provider_secret: bytes, installation_id: str, runtime_id: str) -> str:
    state = _load_provider_state(
        provider_state_path, provider_secret=provider_secret,
        installation_id=installation_id, runtime_id=runtime_id,
    )
    raw = state.get("latest_audit_attestation")
    if raw is None:
        raise ProviderAttestationGuardError("recovery audit attestation missing")
    receipt = _verify_audit_attestation(raw, provider_secret=provider_secret)
    if receipt.installation_id != installation_id or receipt.runtime_id != runtime_id:
        raise ProviderAttestationGuardError("recovery audit scope mismatch")
    if receipt.audit_seq != state["last_audit_seq"] or receipt.audit_hash() != state["last_audit_hash"]:
        raise ProviderAttestationGuardError("recovery audit monotonic floor mismatch")
    current_hash = _canonical_file_hash(recovery_registry_path, label="recovery registry")
    if current_hash != receipt.recovery_registry_sha256:
        raise ProviderAttestationGuardError("RECOVERY_AUDIT_ROLLBACK_OR_TAMPER_DETECTED")
    if receipt.anchor_attestation_hash != state["last_attestation_hash"]:
        raise ProviderAttestationGuardError("recovery audit bound to stale anchor attestation")
    return "RECOVERY_AUDIT_ATTESTED_MATCH"
