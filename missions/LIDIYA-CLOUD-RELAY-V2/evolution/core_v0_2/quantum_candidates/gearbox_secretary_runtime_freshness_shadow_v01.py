from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from gearbox_controller import GearboxGuardError
from gearbox_secretary_signal_shadow_v01 import (
    MISSION_ID,
    PINNED_STEP_ID,
    SecretarySignalEnvelope,
    SecretarySignalProjection,
    NEUTRAL_PRESSURE,
    neutral_secretary_projection,
)

CLOCK_SCHEMA = "0.1-shadow"
SIGNED_SIGNAL_SCHEMA = "0.1-shadow"
CLOCK_SOURCE_ROLE = "RUNTIME_CLOCK_PROVIDER_SHADOW"
CLOCK_PROVIDER_ID = "QUANTUM_RUNTIME_CLOCK_PROVIDER_V01"
CLOCK_KEY_ID = "runtime-clock-hmac-v01"
CLOCK_KEY_SHA256 = "92d8b5ac84412152e5bdab3971a69280f6c34a6d0af0671ebcef77be4265c01d"
SECRETARY_SIGNER_ID = "W07_SECRETARY_SIGNER_SHADOW_V01"
SECRETARY_KEY_ID = "w07-secretary-hmac-v01"
SECRETARY_KEY_SHA256 = "aa2575bbcda5c602759cd911da0fb14b4159794c40f58a5cba531ae4c6b8394e"


class SecretaryFreshnessGuardError(GearboxGuardError):
    pass


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any, *, name: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise SecretaryFreshnessGuardError(f"{name} must be 64-hex sha256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise SecretaryFreshnessGuardError(f"{name} must be 64-hex sha256") from exc
    return value.lower()


def _token(value: Any, *, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value.strip()) > 128:
        raise SecretaryFreshnessGuardError(f"{name} must be explicit bounded string")
    return value.strip()


def _nonnegative_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SecretaryFreshnessGuardError(f"{name} must be nonnegative integer")
    return value


def _validate_secret(secret: Any, *, expected_hash: str, name: str) -> bytes:
    if not isinstance(secret, (bytes, bytearray)) or len(secret) < 32:
        raise SecretaryFreshnessGuardError(f"{name} must be external bytes >=32")
    raw = bytes(secret)
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_hash):
        raise SecretaryFreshnessGuardError(f"{name} fingerprint mismatch")
    return raw


@dataclass(frozen=True)
class RuntimeClockReceipt:
    clock_seq: int
    previous_clock_hash: str
    installation_id: str
    runtime_id: str
    nonce: str
    mac_sha256: str
    source_role: str = CLOCK_SOURCE_ROLE
    provider_id: str = CLOCK_PROVIDER_ID
    key_id: str = CLOCK_KEY_ID
    mission_id: str = MISSION_ID
    step_id: int = PINNED_STEP_ID
    schema_version: str = CLOCK_SCHEMA

    def unsigned_binding(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("mac_sha256")
        return data

    def receipt_hash(self) -> str:
        return hashlib.sha256(_canonical_bytes(asdict(self))).hexdigest()

    @classmethod
    def from_value(cls, value: Any) -> "RuntimeClockReceipt":
        if isinstance(value, cls):
            raw = value
        elif isinstance(value, Mapping):
            try:
                raw = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise SecretaryFreshnessGuardError("malformed runtime clock receipt") from exc
        else:
            raise SecretaryFreshnessGuardError("runtime clock receipt required")
        seq = _nonnegative_int(raw.clock_seq, name="clock_seq")
        previous = _sha256(raw.previous_clock_hash, name="previous_clock_hash")
        installation_id = _token(raw.installation_id, name="installation_id")
        runtime_id = _token(raw.runtime_id, name="runtime_id")
        nonce = _token(raw.nonce, name="nonce")
        mac = _sha256(raw.mac_sha256, name="mac_sha256")
        if raw.source_role != CLOCK_SOURCE_ROLE or raw.provider_id != CLOCK_PROVIDER_ID or raw.key_id != CLOCK_KEY_ID:
            raise SecretaryFreshnessGuardError("runtime clock provider identity mismatch")
        if raw.mission_id != MISSION_ID or raw.step_id != PINNED_STEP_ID or raw.schema_version != CLOCK_SCHEMA:
            raise SecretaryFreshnessGuardError("runtime clock scope/schema mismatch")
        return cls(seq, previous, installation_id, runtime_id, nonce, mac)


def sign_runtime_clock(unsigned: Mapping[str, Any], *, clock_secret: bytes) -> RuntimeClockReceipt:
    secret = _validate_secret(clock_secret, expected_hash=CLOCK_KEY_SHA256, name="clock_secret")
    payload = dict(unsigned)
    payload.pop("mac_sha256", None)
    payload.setdefault("source_role", CLOCK_SOURCE_ROLE)
    payload.setdefault("provider_id", CLOCK_PROVIDER_ID)
    payload.setdefault("key_id", CLOCK_KEY_ID)
    payload.setdefault("mission_id", MISSION_ID)
    payload.setdefault("step_id", PINNED_STEP_ID)
    payload.setdefault("schema_version", CLOCK_SCHEMA)
    payload["mac_sha256"] = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return RuntimeClockReceipt.from_value(payload)


def verify_runtime_clock(value: Any, *, clock_secret: bytes, expected_previous_hash: str,
                         installation_id: str, runtime_id: str,
                         minimum_clock_seq: int) -> RuntimeClockReceipt:
    secret = _validate_secret(clock_secret, expected_hash=CLOCK_KEY_SHA256, name="clock_secret")
    receipt = RuntimeClockReceipt.from_value(value)
    expected_previous_hash = _sha256(expected_previous_hash, name="expected_previous_hash")
    minimum_clock_seq = _nonnegative_int(minimum_clock_seq, name="minimum_clock_seq")
    if receipt.installation_id != installation_id or receipt.runtime_id != runtime_id:
        raise SecretaryFreshnessGuardError("runtime clock scope mismatch")
    if receipt.previous_clock_hash != expected_previous_hash:
        raise SecretaryFreshnessGuardError("runtime clock predecessor mismatch")
    if receipt.clock_seq <= minimum_clock_seq:
        raise SecretaryFreshnessGuardError("runtime clock replay/non-monotonic sequence")
    expected = hmac.new(secret, _canonical_bytes(receipt.unsigned_binding()), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, receipt.mac_sha256):
        raise SecretaryFreshnessGuardError("runtime clock authentication failed")
    return receipt


@dataclass(frozen=True)
class SignedSecretaryObservation:
    signal_fingerprint: str
    signal_id: str
    issued_seq: int
    valid_through_seq: int
    installation_id: str
    runtime_id: str
    mac_sha256: str
    signer_id: str = SECRETARY_SIGNER_ID
    key_id: str = SECRETARY_KEY_ID
    mission_id: str = MISSION_ID
    step_id: int = PINNED_STEP_ID
    schema_version: str = SIGNED_SIGNAL_SCHEMA

    def unsigned_binding(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("mac_sha256")
        return data

    @classmethod
    def from_value(cls, value: Any) -> "SignedSecretaryObservation":
        if isinstance(value, cls):
            raw = value
        elif isinstance(value, Mapping):
            try:
                raw = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise SecretaryFreshnessGuardError("malformed signed secretary observation") from exc
        else:
            raise SecretaryFreshnessGuardError("signed secretary observation required")
        fp = _sha256(raw.signal_fingerprint, name="signal_fingerprint")
        signal_id = _token(raw.signal_id, name="signal_id")
        issued = _nonnegative_int(raw.issued_seq, name="issued_seq")
        valid = _nonnegative_int(raw.valid_through_seq, name="valid_through_seq")
        if issued > valid:
            raise SecretaryFreshnessGuardError("signed observation validity inverted")
        installation_id = _token(raw.installation_id, name="installation_id")
        runtime_id = _token(raw.runtime_id, name="runtime_id")
        mac = _sha256(raw.mac_sha256, name="mac_sha256")
        if raw.signer_id != SECRETARY_SIGNER_ID or raw.key_id != SECRETARY_KEY_ID:
            raise SecretaryFreshnessGuardError("secretary signer identity mismatch")
        if raw.mission_id != MISSION_ID or raw.step_id != PINNED_STEP_ID or raw.schema_version != SIGNED_SIGNAL_SCHEMA:
            raise SecretaryFreshnessGuardError("signed secretary scope/schema mismatch")
        return cls(fp, signal_id, issued, valid, installation_id, runtime_id, mac)


def sign_secretary_observation(envelope_value: Any, *, secretary_secret: bytes) -> SignedSecretaryObservation:
    secret = _validate_secret(secretary_secret, expected_hash=SECRETARY_KEY_SHA256, name="secretary_secret")
    envelope = SecretarySignalEnvelope.from_value(envelope_value)
    payload = {
        "signal_fingerprint": envelope.canonical_fingerprint(),
        "signal_id": envelope.signal_id,
        "issued_seq": envelope.issued_seq,
        "valid_through_seq": envelope.valid_through_seq,
        "installation_id": envelope.installation_id,
        "runtime_id": envelope.runtime_id,
        "signer_id": SECRETARY_SIGNER_ID,
        "key_id": SECRETARY_KEY_ID,
        "mission_id": MISSION_ID,
        "step_id": PINNED_STEP_ID,
        "schema_version": SIGNED_SIGNAL_SCHEMA,
    }
    payload["mac_sha256"] = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return SignedSecretaryObservation.from_value(payload)


def verify_signed_secretary_observation(value: Any, envelope: SecretarySignalEnvelope,
                                        *, secretary_secret: bytes) -> SignedSecretaryObservation:
    secret = _validate_secret(secretary_secret, expected_hash=SECRETARY_KEY_SHA256, name="secretary_secret")
    signed = SignedSecretaryObservation.from_value(value)
    if signed.signal_fingerprint != envelope.canonical_fingerprint() or signed.signal_id != envelope.signal_id:
        raise SecretaryFreshnessGuardError("signed secretary observation binding mismatch")
    if signed.installation_id != envelope.installation_id or signed.runtime_id != envelope.runtime_id:
        raise SecretaryFreshnessGuardError("signed secretary observation scope mismatch")
    if signed.issued_seq != envelope.issued_seq or signed.valid_through_seq != envelope.valid_through_seq:
        raise SecretaryFreshnessGuardError("signed secretary sequence binding mismatch")
    expected = hmac.new(secret, _canonical_bytes(signed.unsigned_binding()), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signed.mac_sha256):
        raise SecretaryFreshnessGuardError("signed secretary authentication failed")
    return signed


def project_secretary_with_runtime_clock_shadow(envelope_value: Any, *, signed_observation: Any,
                                                clock_receipt: Any, clock_secret: bytes,
                                                secretary_secret: bytes, expected_previous_clock_hash: str,
                                                minimum_clock_seq: int,
                                                installation_id: str, runtime_id: str,
                                                authority_conflict: bool = False) -> SecretarySignalProjection:
    """Project secretary telemetry only from an authenticated monotonic runtime clock.

    Caller evaluation_seq has no authority here. A valid clock receipt plus a signal-bound
    W07 signature is required before routing-facing secretary/pressure values are populated.
    This remains shadow-only and creates zero Experience/formal authority.
    """
    if type(authority_conflict) is not bool:
        raise SecretaryFreshnessGuardError("authority_conflict must be bool")
    envelope = SecretarySignalEnvelope.from_value(envelope_value)
    fingerprint = envelope.canonical_fingerprint()
    if envelope.installation_id != installation_id or envelope.runtime_id != runtime_id:
        raise SecretaryFreshnessGuardError("secretary envelope runtime scope mismatch")
    verify_signed_secretary_observation(signed_observation, envelope, secretary_secret=secretary_secret)
    clock = verify_runtime_clock(
        clock_receipt, clock_secret=clock_secret,
        expected_previous_hash=expected_previous_clock_hash,
        installation_id=installation_id, runtime_id=runtime_id,
        minimum_clock_seq=minimum_clock_seq,
    )
    if authority_conflict:
        return neutral_secretary_projection(
            status="AUTHORITY_CONFLICT_ZERO_EFFECT_AUTHENTICATED_CLOCK",
            signal_id=envelope.signal_id, fingerprint=fingerprint,
            dropped_fields=tuple(sorted(envelope.measurements.keys())),
        )
    if clock.clock_seq < envelope.issued_seq:
        return neutral_secretary_projection(
            status="FUTURE_ENVELOPE_ZERO_EFFECT_AUTHENTICATED_CLOCK",
            signal_id=envelope.signal_id, fingerprint=fingerprint,
            dropped_fields=tuple(sorted(envelope.measurements.keys())),
        )
    if clock.clock_seq > envelope.valid_through_seq:
        return neutral_secretary_projection(
            status="STALE_ENVELOPE_ZERO_EFFECT_AUTHENTICATED_CLOCK",
            signal_id=envelope.signal_id, fingerprint=fingerprint,
            dropped_fields=tuple(sorted(envelope.measurements.keys())),
        )

    observed = dict(NEUTRAL_PRESSURE)
    accepted: list[str] = []
    dropped: list[str] = []
    for field_name in sorted(NEUTRAL_PRESSURE):
        measurement = envelope.measurements.get(field_name)
        if measurement is None:
            dropped.append(field_name)
        elif measurement.observed_seq <= clock.clock_seq <= measurement.valid_through_seq:
            observed[field_name] = measurement.value
            accepted.append(field_name)
        else:
            dropped.append(field_name)

    if not accepted:
        return neutral_secretary_projection(
            status="NO_FRESH_FIELDS_ZERO_EFFECT_AUTHENTICATED_CLOCK",
            signal_id=envelope.signal_id, fingerprint=fingerprint,
            dropped_fields=tuple(dropped),
        )
    return SecretarySignalProjection(
        signal_id=envelope.signal_id,
        envelope_fingerprint=fingerprint,
        observed_secretary_level=envelope.secretary_level,
        observed_pressure_inputs=observed,
        routing_secretary_level=envelope.secretary_level,
        routing_pressure_inputs=dict(observed),
        accepted_fields=tuple(accepted),
        dropped_fields=tuple(dropped),
        status="AUTHENTICATED_RUNTIME_FRESH_ROUTING_SHADOW",
        routing_authority_allowed=True,
        formal_mutation_allowed=False,
        verified_experience_delta=0,
        operational_progress_delta=0,
    )
