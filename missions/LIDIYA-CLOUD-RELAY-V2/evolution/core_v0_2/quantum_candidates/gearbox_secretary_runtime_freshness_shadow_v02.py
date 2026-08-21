from __future__ import annotations

import hashlib
import hmac
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from gearbox_secretary_runtime_freshness_shadow_v01 import (
    CLOCK_KEY_ID,
    CLOCK_KEY_SHA256,
    CLOCK_PROVIDER_ID,
    CLOCK_SOURCE_ROLE,
    CLOCK_SCHEMA,
    SecretaryFreshnessGuardError,
    RuntimeClockReceipt,
    _canonical_bytes,
    _nonnegative_int,
    _sha256,
    _token,
    _validate_secret,
    project_secretary_with_runtime_clock_shadow as _project_v01,
)
from gearbox_secretary_signal_shadow_v01 import MISSION_ID, PINNED_STEP_ID, SecretarySignalProjection

CHECKPOINT_SCHEMA = "0.2-shadow"
ZERO_HASH = "0" * 64


@dataclass(frozen=True)
class RuntimeClockCheckpoint:
    last_clock_seq: int
    last_clock_hash: str
    installation_id: str
    runtime_id: str
    checkpoint_nonce: str
    mac_sha256: str
    source_role: str = CLOCK_SOURCE_ROLE
    provider_id: str = CLOCK_PROVIDER_ID
    key_id: str = CLOCK_KEY_ID
    mission_id: str = MISSION_ID
    step_id: int = PINNED_STEP_ID
    schema_version: str = CHECKPOINT_SCHEMA

    def unsigned_binding(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("mac_sha256")
        return data

    @classmethod
    def from_value(cls, value: Any) -> "RuntimeClockCheckpoint":
        if isinstance(value, cls):
            raw = value
        elif isinstance(value, Mapping):
            try:
                raw = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise SecretaryFreshnessGuardError("malformed runtime clock checkpoint") from exc
        else:
            raise SecretaryFreshnessGuardError("runtime clock checkpoint required")
        seq = _nonnegative_int(raw.last_clock_seq, name="last_clock_seq")
        last_hash = _sha256(raw.last_clock_hash, name="last_clock_hash")
        installation_id = _token(raw.installation_id, name="installation_id")
        runtime_id = _token(raw.runtime_id, name="runtime_id")
        nonce = _token(raw.checkpoint_nonce, name="checkpoint_nonce")
        mac = _sha256(raw.mac_sha256, name="mac_sha256")
        if seq == 0 and last_hash != ZERO_HASH:
            raise SecretaryFreshnessGuardError("zero clock checkpoint must use zero hash")
        if raw.source_role != CLOCK_SOURCE_ROLE or raw.provider_id != CLOCK_PROVIDER_ID or raw.key_id != CLOCK_KEY_ID:
            raise SecretaryFreshnessGuardError("clock checkpoint provider identity mismatch")
        if raw.mission_id != MISSION_ID or raw.step_id != PINNED_STEP_ID or raw.schema_version != CHECKPOINT_SCHEMA:
            raise SecretaryFreshnessGuardError("clock checkpoint scope/schema mismatch")
        return cls(seq, last_hash, installation_id, runtime_id, nonce, mac)


def sign_clock_checkpoint(unsigned: Mapping[str, Any], *, clock_secret: bytes) -> RuntimeClockCheckpoint:
    secret = _validate_secret(clock_secret, expected_hash=CLOCK_KEY_SHA256, name="clock_secret")
    payload = dict(unsigned)
    payload.pop("mac_sha256", None)
    payload.setdefault("source_role", CLOCK_SOURCE_ROLE)
    payload.setdefault("provider_id", CLOCK_PROVIDER_ID)
    payload.setdefault("key_id", CLOCK_KEY_ID)
    payload.setdefault("mission_id", MISSION_ID)
    payload.setdefault("step_id", PINNED_STEP_ID)
    payload.setdefault("schema_version", CHECKPOINT_SCHEMA)
    payload["mac_sha256"] = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return RuntimeClockCheckpoint.from_value(payload)


def verify_clock_checkpoint(value: Any, *, clock_secret: bytes,
                            installation_id: str, runtime_id: str) -> RuntimeClockCheckpoint:
    secret = _validate_secret(clock_secret, expected_hash=CLOCK_KEY_SHA256, name="clock_secret")
    checkpoint = RuntimeClockCheckpoint.from_value(value)
    if checkpoint.installation_id != installation_id or checkpoint.runtime_id != runtime_id:
        raise SecretaryFreshnessGuardError("clock checkpoint scope mismatch")
    expected = hmac.new(secret, _canonical_bytes(checkpoint.unsigned_binding()), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, checkpoint.mac_sha256):
        raise SecretaryFreshnessGuardError("clock checkpoint authentication failed")
    return checkpoint


def advance_clock_checkpoint(checkpoint_value: Any, receipt_value: Any, *, clock_secret: bytes,
                             installation_id: str, runtime_id: str,
                             checkpoint_nonce: str) -> RuntimeClockCheckpoint:
    checkpoint = verify_clock_checkpoint(
        checkpoint_value, clock_secret=clock_secret,
        installation_id=installation_id, runtime_id=runtime_id,
    )
    receipt = RuntimeClockReceipt.from_value(receipt_value)
    if receipt.installation_id != installation_id or receipt.runtime_id != runtime_id:
        raise SecretaryFreshnessGuardError("runtime clock scope mismatch")
    if receipt.previous_clock_hash != checkpoint.last_clock_hash:
        raise SecretaryFreshnessGuardError("runtime clock predecessor mismatch")
    if receipt.clock_seq <= checkpoint.last_clock_seq:
        raise SecretaryFreshnessGuardError("runtime clock replay/non-monotonic sequence")
    # v01 verification authenticates the exact receipt; checkpoint values are no longer caller facts.
    from gearbox_secretary_runtime_freshness_shadow_v01 import verify_runtime_clock
    verified = verify_runtime_clock(
        receipt, clock_secret=clock_secret,
        expected_previous_hash=checkpoint.last_clock_hash,
        installation_id=installation_id, runtime_id=runtime_id,
        minimum_clock_seq=checkpoint.last_clock_seq,
    )
    return sign_clock_checkpoint({
        "last_clock_seq": verified.clock_seq,
        "last_clock_hash": verified.receipt_hash(),
        "installation_id": installation_id,
        "runtime_id": runtime_id,
        "checkpoint_nonce": checkpoint_nonce,
    }, clock_secret=clock_secret)


def project_secretary_with_authenticated_checkpoint_shadow(
    envelope_value: Any, *, signed_observation: Any, clock_receipt: Any,
    clock_checkpoint: Any, clock_secret: bytes, secretary_secret: bytes,
    installation_id: str, runtime_id: str, authority_conflict: bool = False,
) -> SecretarySignalProjection:
    """Authoritative shadow freshness path: no naked caller sequence/hash floor exists."""
    checkpoint = verify_clock_checkpoint(
        clock_checkpoint, clock_secret=clock_secret,
        installation_id=installation_id, runtime_id=runtime_id,
    )
    return _project_v01(
        envelope_value,
        signed_observation=signed_observation,
        clock_receipt=clock_receipt,
        clock_secret=clock_secret,
        secretary_secret=secretary_secret,
        expected_previous_clock_hash=checkpoint.last_clock_hash,
        minimum_clock_seq=checkpoint.last_clock_seq,
        installation_id=installation_id,
        runtime_id=runtime_id,
        authority_conflict=authority_conflict,
    )
