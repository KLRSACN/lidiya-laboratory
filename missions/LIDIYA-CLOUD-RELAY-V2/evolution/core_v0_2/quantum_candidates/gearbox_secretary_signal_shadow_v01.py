from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from pathlib import Path as _Path
import sys as _sys

_HERE = _Path(__file__).resolve().parent
if str(_HERE) not in _sys.path:
    _sys.path.insert(0, str(_HERE))
_EVOLUTION = _HERE.parents[1]
if str(_EVOLUTION) not in _sys.path:
    _sys.path.insert(0, str(_EVOLUTION))

from gearbox_controller import GearboxGuardError
from gearbox_controller_v2 import strict_bool
from gearbox_authority_projection_shadow_v01 import canonical_git_blob_sha
from gearbox_v2_1_repair_shadow_v01 import MISSION_ID, canonical_event_id

SECRETARY_SCHEMA = "1.0-shadow"
SECRETARY_SOURCE_ROLE = "W07"
SECRETARY_AUTHORITY = "NONE"
SECRETARY_LEVELS = {"GREEN", "YELLOW", "ORANGE", "RED"}
PINNED_STEP_ID = 9
PINNED_SECRETARY_PROTOCOL_BLOB_SHA = "0e4ba4108ca9953a566e3ea5ca4957e1ee6d142b"

PRESSURE_FIELDS = {
    "context_load_ratio",
    "tool_failure_ratio",
    "stale_pointer_ratio",
    "durable_progress_age_ratio",
    "continuity_anchor_health",
    "storage_pressure_ratio",
}

NEUTRAL_PRESSURE = {
    "context_load_ratio": 0.0,
    "tool_failure_ratio": 0.0,
    "stale_pointer_ratio": 0.0,
    "durable_progress_age_ratio": 0.0,
    "continuity_anchor_health": 1.0,
    "storage_pressure_ratio": 0.0,
}


def _bounded_token(value: Any, *, name: str) -> str:
    if type(value) is not str:
        raise GearboxGuardError(f"{name} must be explicit string")
    token = value.strip()
    if not token or len(token) > 128:
        raise GearboxGuardError(f"{name} must be non-empty and <=128 chars")
    return token


def _nonnegative_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GearboxGuardError(f"{name} must be nonnegative integer")
    return value


def _ratio(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GearboxGuardError(f"{name} must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise GearboxGuardError(f"{name} must be in [0,1]")
    return result


def _secretary_level(value: Any) -> str:
    if type(value) is not str:
        raise GearboxGuardError("secretary_level must be explicit string")
    level = value.strip().upper()
    if level not in SECRETARY_LEVELS:
        raise GearboxGuardError("invalid secretary_level")
    return level


@dataclass(frozen=True)
class SecretaryFieldMeasurement:
    value: float
    source_role: str
    sensor_id: str
    observed_seq: int
    valid_through_seq: int
    installation_id: str
    runtime_id: str

    @classmethod
    def from_value(
        cls,
        value: Any,
        *,
        field_name: str,
        envelope_installation_id: str,
        envelope_runtime_id: str,
        envelope_valid_through_seq: int,
    ) -> "SecretaryFieldMeasurement":
        if not isinstance(value, Mapping):
            raise GearboxGuardError(f"{field_name} measurement must be mapping")
        required = {
            "value", "source_role", "sensor_id", "observed_seq", "valid_through_seq",
            "installation_id", "runtime_id",
        }
        if set(value.keys()) != required:
            raise GearboxGuardError(f"{field_name} measurement has unexpected/missing keys")

        ratio = _ratio(value["value"], name=field_name)
        source_role = _bounded_token(value["source_role"], name=f"{field_name}.source_role")
        sensor_id = _bounded_token(value["sensor_id"], name=f"{field_name}.sensor_id")
        observed_seq = _nonnegative_int(value["observed_seq"], name=f"{field_name}.observed_seq")
        valid_through_seq = _nonnegative_int(
            value["valid_through_seq"], name=f"{field_name}.valid_through_seq"
        )
        installation_id = _bounded_token(
            value["installation_id"], name=f"{field_name}.installation_id"
        )
        runtime_id = _bounded_token(value["runtime_id"], name=f"{field_name}.runtime_id")

        if source_role != SECRETARY_SOURCE_ROLE:
            raise GearboxGuardError(f"{field_name} source_role must be W07")
        if installation_id != envelope_installation_id or runtime_id != envelope_runtime_id:
            raise GearboxGuardError(f"{field_name} provenance does not match envelope runtime")
        if observed_seq > valid_through_seq:
            raise GearboxGuardError(f"{field_name} observed_seq exceeds valid_through_seq")
        if valid_through_seq > envelope_valid_through_seq:
            raise GearboxGuardError(f"{field_name} validity exceeds envelope validity")

        return cls(
            value=ratio,
            source_role=source_role,
            sensor_id=sensor_id,
            observed_seq=observed_seq,
            valid_through_seq=valid_through_seq,
            installation_id=installation_id,
            runtime_id=runtime_id,
        )


@dataclass(frozen=True)
class SecretarySignalEnvelope:
    schema_version: str
    mission_id: str
    step_id: int
    source_role: str
    authority: str
    protocol_blob_sha: str
    signal_id: str
    installation_id: str
    runtime_id: str
    issued_seq: int
    valid_through_seq: int
    secretary_level: str
    measurements: dict[str, SecretaryFieldMeasurement]

    @classmethod
    def from_value(cls, value: Any) -> "SecretarySignalEnvelope":
        if not isinstance(value, Mapping):
            raise GearboxGuardError("SecretarySignalEnvelope required")
        required = {
            "schema_version", "mission_id", "step_id", "source_role", "authority",
            "protocol_blob_sha", "signal_id", "installation_id", "runtime_id",
            "issued_seq", "valid_through_seq", "secretary_level", "measurements",
        }
        if set(value.keys()) != required:
            raise GearboxGuardError("SecretarySignalEnvelope has unexpected/missing keys")
        if value["schema_version"] != SECRETARY_SCHEMA:
            raise GearboxGuardError("unsupported SecretarySignalEnvelope schema")
        if value["mission_id"] != MISSION_ID:
            raise GearboxGuardError("secretary mission mismatch")
        step_id = _nonnegative_int(value["step_id"], name="secretary step_id")
        if step_id != PINNED_STEP_ID:
            raise GearboxGuardError("secretary step mismatch; shadow rebase required")
        source_role = _bounded_token(value["source_role"], name="secretary source_role")
        if source_role != SECRETARY_SOURCE_ROLE:
            raise GearboxGuardError("untrusted secretary source role")
        authority = _bounded_token(value["authority"], name="secretary authority").upper()
        if authority != SECRETARY_AUTHORITY:
            raise GearboxGuardError("secretary must remain sensor-only with authority NONE")
        protocol_blob_sha = canonical_git_blob_sha(
            value["protocol_blob_sha"], name="secretary protocol_blob_sha"
        )
        if protocol_blob_sha != PINNED_SECRETARY_PROTOCOL_BLOB_SHA:
            raise GearboxGuardError("secretary protocol snapshot mismatch; shadow rebase required")
        signal_id = canonical_event_id(value["signal_id"])
        installation_id = _bounded_token(value["installation_id"], name="secretary installation_id")
        runtime_id = _bounded_token(value["runtime_id"], name="secretary runtime_id")
        issued_seq = _nonnegative_int(value["issued_seq"], name="secretary issued_seq")
        valid_through_seq = _nonnegative_int(
            value["valid_through_seq"], name="secretary valid_through_seq"
        )
        if issued_seq > valid_through_seq:
            raise GearboxGuardError("secretary issued_seq exceeds valid_through_seq")
        level = _secretary_level(value["secretary_level"])

        measurements_raw = value["measurements"]
        if not isinstance(measurements_raw, Mapping):
            raise GearboxGuardError("secretary measurements must be mapping")
        unknown = set(measurements_raw.keys()) - PRESSURE_FIELDS
        if unknown:
            raise GearboxGuardError("unknown secretary pressure field")

        measurements: dict[str, SecretaryFieldMeasurement] = {}
        for field_name, measurement in measurements_raw.items():
            measurements[field_name] = SecretaryFieldMeasurement.from_value(
                measurement,
                field_name=field_name,
                envelope_installation_id=installation_id,
                envelope_runtime_id=runtime_id,
                envelope_valid_through_seq=valid_through_seq,
            )

        return cls(
            schema_version=SECRETARY_SCHEMA,
            mission_id=MISSION_ID,
            step_id=PINNED_STEP_ID,
            source_role=source_role,
            authority=SECRETARY_AUTHORITY,
            protocol_blob_sha=protocol_blob_sha,
            signal_id=signal_id,
            installation_id=installation_id,
            runtime_id=runtime_id,
            issued_seq=issued_seq,
            valid_through_seq=valid_through_seq,
            secretary_level=level,
            measurements=measurements,
        )

    def canonical_fingerprint(self) -> str:
        payload = {
            **{k: v for k, v in asdict(self).items() if k != "measurements"},
            "measurements": {
                name: asdict(measurement)
                for name, measurement in sorted(self.measurements.items())
            },
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SecretarySignalProjection:
    signal_id: str | None
    envelope_fingerprint: str | None
    secretary_level: str
    pressure_inputs: dict[str, float]
    accepted_fields: tuple[str, ...]
    dropped_fields: tuple[str, ...]
    status: str
    routing_authority_allowed: bool
    formal_mutation_allowed: bool
    verified_experience_delta: int
    operational_progress_delta: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def neutral_secretary_projection(*, status: str, signal_id: str | None = None,
                                fingerprint: str | None = None,
                                dropped_fields: tuple[str, ...] = ()) -> SecretarySignalProjection:
    return SecretarySignalProjection(
        signal_id=signal_id,
        envelope_fingerprint=fingerprint,
        secretary_level="UNKNOWN",
        pressure_inputs=dict(NEUTRAL_PRESSURE),
        accepted_fields=(),
        dropped_fields=dropped_fields,
        status=status,
        routing_authority_allowed=False,
        formal_mutation_allowed=False,
        verified_experience_delta=0,
        operational_progress_delta=0,
    )


def project_secretary_signal_shadow(
    envelope_value: Any,
    *,
    trusted_current_seq: int,
    authority_conflict: bool = False,
) -> SecretarySignalProjection:
    """Validate secretary telemetry and sanitize each pressure field independently.

    This tranche deliberately does not grant routing authority. It proves envelope and
    per-field provenance/freshness semantics only. A future trusted runtime freshness
    root must bind ``trusted_current_seq`` before any projection can affect routing.
    Until then, sanitized values are observational evidence only.
    """
    current_seq = _nonnegative_int(trusted_current_seq, name="trusted_current_seq")
    conflict = strict_bool(authority_conflict, "authority_conflict")
    envelope = SecretarySignalEnvelope.from_value(envelope_value)
    fingerprint = envelope.canonical_fingerprint()

    if conflict:
        return neutral_secretary_projection(
            status="AUTHORITY_CONFLICT_ZERO_EFFECT",
            signal_id=envelope.signal_id,
            fingerprint=fingerprint,
            dropped_fields=tuple(sorted(envelope.measurements.keys())),
        )

    if current_seq < envelope.issued_seq:
        return neutral_secretary_projection(
            status="FUTURE_ENVELOPE_ZERO_EFFECT",
            signal_id=envelope.signal_id,
            fingerprint=fingerprint,
            dropped_fields=tuple(sorted(envelope.measurements.keys())),
        )
    if current_seq > envelope.valid_through_seq:
        return neutral_secretary_projection(
            status="STALE_ENVELOPE_ZERO_EFFECT",
            signal_id=envelope.signal_id,
            fingerprint=fingerprint,
            dropped_fields=tuple(sorted(envelope.measurements.keys())),
        )

    pressure = dict(NEUTRAL_PRESSURE)
    accepted: list[str] = []
    dropped: list[str] = []

    for field_name in sorted(PRESSURE_FIELDS):
        measurement = envelope.measurements.get(field_name)
        if measurement is None:
            dropped.append(field_name)
            continue
        if measurement.observed_seq <= current_seq <= measurement.valid_through_seq:
            pressure[field_name] = measurement.value
            accepted.append(field_name)
        else:
            dropped.append(field_name)

    status = "FRESH_FIELDS_OBSERVATIONAL_ONLY" if accepted else "NO_FRESH_FIELDS_ZERO_EFFECT"
    return SecretarySignalProjection(
        signal_id=envelope.signal_id,
        envelope_fingerprint=fingerprint,
        secretary_level=envelope.secretary_level if accepted else "UNKNOWN",
        pressure_inputs=pressure,
        accepted_fields=tuple(accepted),
        dropped_fields=tuple(dropped),
        status=status,
        routing_authority_allowed=False,
        formal_mutation_allowed=False,
        verified_experience_delta=0,
        operational_progress_delta=0,
    )
