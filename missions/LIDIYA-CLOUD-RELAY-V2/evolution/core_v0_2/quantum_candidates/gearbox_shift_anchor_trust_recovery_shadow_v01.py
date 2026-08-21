from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

# Non-formal shadow research only. No MISSION_STATE mutation, no LCR-C PASS.

from gearbox_shift_durability_anchor_shadow_v01 import (
    ANCHOR_SCHEMA_VERSION,
    ZERO_HASH,
    DurabilityAnchorGuardError,
    ExternalMonotonicAnchorReceipt,
    _anchor_file_payload,
    _atomic_save,
    _ledger_snapshot,
    _load_anchor,
    exclusive_writer_lock,
    verify_anchor,
)
from gearbox_shift_history_shadow_v01 import MISSION_ID, STEP_ID

RECOVERY_SCHEMA_VERSION = "0.1-shadow"
RECOVERY_INCIDENT_KIND = "UNANCHORED_LEDGER_ADVANCE_CRASH_WINDOW"
PROVIDER_ID = "QUANTUM_SHADOW_MONOTONIC_PROVIDER_V01"
PROVIDER_KEY_ID = "shadow-hmac-key-v01"
PROVIDER_DOMAIN_ID = "trusted-anchor-domain-A"
# Synthetic public-test provider fingerprint. The corresponding test secret is not a
# production credential and this constant does not establish a real external trust root.
PROVIDER_KEY_SHA256 = "f25ae1918473a8a612f9182338024217d4c815b672dd1b81c45a1038e9e706b0"
RECOVERY_REGISTRY_SCHEMA = "0.1-shadow"


class AnchorRecoveryGuardError(ValueError):
    pass


def _explicit_string(value: Any, *, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise AnchorRecoveryGuardError(f"{name} must be explicit non-empty string")
    return value.strip()


def _nonnegative_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnchorRecoveryGuardError(f"{name} must be nonnegative integer")
    return value


def _sha256(value: Any, *, name: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise AnchorRecoveryGuardError(f"{name} must be 64-hex sha256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise AnchorRecoveryGuardError(f"{name} must be 64-hex sha256") from exc
    return value.lower()


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _validate_provider_secret(secret: Any) -> bytes:
    if not isinstance(secret, (bytes, bytearray)) or len(secret) < 32:
        raise AnchorRecoveryGuardError("provider secret must be external bytes >=32")
    raw = bytes(secret)
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), PROVIDER_KEY_SHA256):
        raise AnchorRecoveryGuardError("provider trust-key fingerprint mismatch")
    return raw


@dataclass(frozen=True)
class AuthenticatedCrashRecoveryReceipt:
    recovery_id: str
    previous_anchor_hash: str
    observed_anchor_seq: int
    observed_anchor_head_hash: str
    observed_ledger_seq: int
    observed_ledger_head_hash: str
    installation_id: str
    runtime_id: str
    nonce: str
    mac_sha256: str
    incident_kind: str = RECOVERY_INCIDENT_KIND
    provider_id: str = PROVIDER_ID
    provider_key_id: str = PROVIDER_KEY_ID
    durability_domain_id: str = PROVIDER_DOMAIN_ID
    mission_id: str = MISSION_ID
    step_id: int = STEP_ID
    schema_version: str = RECOVERY_SCHEMA_VERSION

    def unsigned_binding(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("mac_sha256")
        return data

    def receipt_hash(self) -> str:
        return _payload_hash(asdict(self))

    @classmethod
    def from_value(cls, value: Any) -> "AuthenticatedCrashRecoveryReceipt":
        if isinstance(value, cls):
            receipt = value
        elif isinstance(value, Mapping):
            try:
                receipt = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise AnchorRecoveryGuardError("malformed recovery receipt") from exc
        else:
            raise AnchorRecoveryGuardError("recovery receipt must be mapping or receipt")
        recovery_id = _explicit_string(receipt.recovery_id, name="recovery_id")
        nonce = _explicit_string(receipt.nonce, name="nonce")
        previous = _sha256(receipt.previous_anchor_hash, name="previous_anchor_hash")
        anchor_head = _sha256(receipt.observed_anchor_head_hash, name="observed_anchor_head_hash")
        ledger_head = _sha256(receipt.observed_ledger_head_hash, name="observed_ledger_head_hash")
        mac = _sha256(receipt.mac_sha256, name="mac_sha256")
        anchor_seq = _nonnegative_int(receipt.observed_anchor_seq, name="observed_anchor_seq")
        ledger_seq = _nonnegative_int(receipt.observed_ledger_seq, name="observed_ledger_seq")
        installation_id = _explicit_string(receipt.installation_id, name="installation_id")
        runtime_id = _explicit_string(receipt.runtime_id, name="runtime_id")
        if receipt.incident_kind != RECOVERY_INCIDENT_KIND:
            raise AnchorRecoveryGuardError("recovery incident kind mismatch")
        if receipt.provider_id != PROVIDER_ID or receipt.provider_key_id != PROVIDER_KEY_ID:
            raise AnchorRecoveryGuardError("provider identity mismatch")
        if receipt.durability_domain_id != PROVIDER_DOMAIN_ID:
            raise AnchorRecoveryGuardError("provider durability domain mismatch")
        if receipt.mission_id != MISSION_ID or receipt.step_id != STEP_ID:
            raise AnchorRecoveryGuardError("recovery mission/step mismatch")
        if receipt.schema_version != RECOVERY_SCHEMA_VERSION:
            raise AnchorRecoveryGuardError("recovery schema mismatch")
        return cls(
            recovery_id, previous, anchor_seq, anchor_head, ledger_seq, ledger_head,
            installation_id, runtime_id, nonce, mac,
        )


def sign_recovery_receipt(unsigned: Mapping[str, Any], *, provider_secret: bytes) -> AuthenticatedCrashRecoveryReceipt:
    secret = _validate_provider_secret(provider_secret)
    payload = dict(unsigned)
    payload.pop("mac_sha256", None)
    payload.setdefault("incident_kind", RECOVERY_INCIDENT_KIND)
    payload.setdefault("provider_id", PROVIDER_ID)
    payload.setdefault("provider_key_id", PROVIDER_KEY_ID)
    payload.setdefault("durability_domain_id", PROVIDER_DOMAIN_ID)
    payload.setdefault("mission_id", MISSION_ID)
    payload.setdefault("step_id", STEP_ID)
    payload.setdefault("schema_version", RECOVERY_SCHEMA_VERSION)
    mac = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    payload["mac_sha256"] = mac
    return AuthenticatedCrashRecoveryReceipt.from_value(payload)


def verify_recovery_receipt(value: Any, *, provider_secret: bytes) -> AuthenticatedCrashRecoveryReceipt:
    secret = _validate_provider_secret(provider_secret)
    receipt = AuthenticatedCrashRecoveryReceipt.from_value(value)
    expected = hmac.new(secret, _canonical_bytes(receipt.unsigned_binding()), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, receipt.mac_sha256):
        raise AnchorRecoveryGuardError("recovery receipt authentication failed")
    return receipt


def _load_recovery_registry(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnchorRecoveryGuardError("recovery registry unreadable") from exc
    if not isinstance(data, dict) or data.get("schema_version") != RECOVERY_REGISTRY_SCHEMA:
        raise AnchorRecoveryGuardError("recovery registry schema mismatch")
    receipts = data.get("receipts")
    if not isinstance(receipts, dict) or not all(type(k) is str and type(v) is str for k, v in receipts.items()):
        raise AnchorRecoveryGuardError("recovery registry malformed")
    return dict(receipts)


def _save_recovery_registry(path: Path, receipts: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": RECOVERY_REGISTRY_SCHEMA, "receipts": dict(receipts)}, handle,
                      ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@dataclass(frozen=True)
class RecoveryResult:
    status: str
    ledger_seq: int
    anchor_seq: int
    ledger_head_hash: str
    anchor_hash: str
    provider_id: str = PROVIDER_ID
    live_routing_authority_allowed: bool = False
    formal_mutation_allowed: bool = False
    experience_delta: int = 0
    operational_progress_delta: int = 0


def recover_unanchored_advance(*, receipt: Any, provider_secret: bytes,
                               registry_path: Path, anchor_path: Path, lock_path: Path,
                               recovery_registry_path: Path, installation_id: str, runtime_id: str) -> RecoveryResult:
    """Authenticate exactly one crash-window anchor advance; never bless arbitrary divergence.

    Recovery is allowed only when the ledger is exactly one accepted event ahead of the
    authenticated previous anchor and the provider-signed receipt binds the exact old
    anchor plus exact current ledger. This is shadow semantics, not production trust.
    """
    verified_receipt = verify_recovery_receipt(receipt, provider_secret=provider_secret)
    if verified_receipt.installation_id != installation_id or verified_receipt.runtime_id != runtime_id:
        raise AnchorRecoveryGuardError("recovery scope mismatch")

    with exclusive_writer_lock(lock_path):
        receipts = _load_recovery_registry(recovery_registry_path)
        receipt_hash = verified_receipt.receipt_hash()
        prior = receipts.get(verified_receipt.recovery_id)
        if prior is not None and prior != receipt_hash:
            raise AnchorRecoveryGuardError("RECOVERY_IDENTITY_CONFLICT")

        anchor = _load_anchor(
            anchor_path, installation_id=installation_id, runtime_id=runtime_id,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        )
        ledger_seq, ledger_head = _ledger_snapshot(
            registry_path, installation_id=installation_id, runtime_id=runtime_id,
        )

        # Crash after anchor write but before recovery-registry write: authenticate and
        # finish the audit record as an idempotent replay.
        if ledger_seq == anchor.anchor_seq and ledger_head == anchor.ledger_head_hash:
            if (anchor.anchor_seq == verified_receipt.observed_ledger_seq and
                    anchor.ledger_head_hash == verified_receipt.observed_ledger_head_hash and
                    anchor.previous_anchor_hash == verified_receipt.previous_anchor_hash):
                receipts[verified_receipt.recovery_id] = receipt_hash
                _save_recovery_registry(recovery_registry_path, receipts)
                return RecoveryResult("RECOVERY_ALREADY_APPLIED_NO_OP", ledger_seq, anchor.anchor_seq,
                                      ledger_head, anchor.anchor_hash())
            raise AnchorRecoveryGuardError("recovery receipt does not match current anchored state")

        status = verify_anchor(
            registry_path=registry_path, anchor_path=anchor_path,
            installation_id=installation_id, runtime_id=runtime_id,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        )
        if status.status != "UNANCHORED_LEDGER_ADVANCE":
            raise AnchorRecoveryGuardError(f"recovery not allowed from {status.status}")
        if ledger_seq != anchor.anchor_seq + 1:
            raise AnchorRecoveryGuardError("recovery only permits exactly one unanchored ledger advance")
        if verified_receipt.previous_anchor_hash != anchor.anchor_hash():
            raise AnchorRecoveryGuardError("recovery previous anchor mismatch")
        if verified_receipt.observed_anchor_seq != anchor.anchor_seq:
            raise AnchorRecoveryGuardError("recovery anchor sequence mismatch")
        if verified_receipt.observed_anchor_head_hash != anchor.ledger_head_hash:
            raise AnchorRecoveryGuardError("recovery anchor head mismatch")
        if verified_receipt.observed_ledger_seq != ledger_seq or verified_receipt.observed_ledger_head_hash != ledger_head:
            raise AnchorRecoveryGuardError("recovery ledger observation mismatch")

        next_anchor = ExternalMonotonicAnchorReceipt(
            anchor_seq=ledger_seq,
            ledger_head_hash=ledger_head,
            installation_id=installation_id,
            runtime_id=runtime_id,
            durability_domain_id=PROVIDER_DOMAIN_ID,
            previous_anchor_hash=anchor.anchor_hash(),
        )
        _atomic_save(anchor_path, _anchor_file_payload(next_anchor))
        receipts[verified_receipt.recovery_id] = receipt_hash
        _save_recovery_registry(recovery_registry_path, receipts)

        final = verify_anchor(
            registry_path=registry_path, anchor_path=anchor_path,
            installation_id=installation_id, runtime_id=runtime_id,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        )
        if final.status != "ANCHOR_MATCH":
            raise AnchorRecoveryGuardError(final.status)
        return RecoveryResult("RECOVERY_APPLIED", final.ledger_seq, final.anchor_seq,
                              final.ledger_head_hash, next_anchor.anchor_hash())
