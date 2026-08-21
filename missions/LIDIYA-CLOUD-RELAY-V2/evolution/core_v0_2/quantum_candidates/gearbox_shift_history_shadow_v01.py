from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

# Non-formal shadow research only. This module does not mutate MISSION_STATE,
# does not replace Gearbox v1/v2/v2.1, and does not claim LCR-C verification.

MISSION_ID = "LCR-EVOLUTION-0005"
STEP_ID = 9
SCHEMA_VERSION = "0.1-shadow"
SOURCE_ROLE = "RUNTIME_SHIFT_LEDGER_SHADOW"
GEAR_STATES = {"G1", "G2", "G3", "G4", "G5", "G6"}
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
ZERO_HASH = "0" * 64


class ShiftHistoryGuardError(ValueError):
    pass


def _explicit_string(value: Any, *, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ShiftHistoryGuardError(f"{name} must be explicit non-empty string")
    return value.strip()


def _event_id(value: Any) -> str:
    value = _explicit_string(value, name="event_id")
    if not EVENT_ID_RE.fullmatch(value):
        raise ShiftHistoryGuardError("event_id must match bounded canonical token syntax")
    return value


def _sha256(value: Any, *, name: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise ShiftHistoryGuardError(f"{name} must be 64-hex sha256")
    return value.lower()


def _nonnegative_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ShiftHistoryGuardError(f"{name} must be nonnegative integer")
    return value


def _positive_int(value: Any, *, name: str) -> int:
    value = _nonnegative_int(value, name=name)
    if value == 0:
        raise ShiftHistoryGuardError(f"{name} must be positive integer")
    return value


def _ratio(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ShiftHistoryGuardError(f"{name} must be numeric")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ShiftHistoryGuardError(f"{name} must be in [0,1]")
    return value


def _gear(value: Any, *, name: str) -> str:
    value = _explicit_string(value, name=name).upper()
    if value not in GEAR_STATES:
        raise ShiftHistoryGuardError(f"{name} must be G1..G6")
    return value


def _hash_payload(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ShiftEventReceipt:
    event_id: str
    seq: int
    from_gear: str
    to_gear: str
    evidence_sha256: str
    previous_event_hash: str
    installation_id: str
    runtime_id: str
    mission_id: str = MISSION_ID
    step_id: int = STEP_ID
    source_role: str = SOURCE_ROLE

    @classmethod
    def from_value(cls, value: Any) -> "ShiftEventReceipt":
        if isinstance(value, cls):
            raw = value
        elif isinstance(value, Mapping):
            try:
                raw = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise ShiftHistoryGuardError("malformed shift event receipt") from exc
        else:
            raise ShiftHistoryGuardError("shift event receipt must be mapping or ShiftEventReceipt")

        event_id = _event_id(raw.event_id)
        seq = _positive_int(raw.seq, name="seq")
        from_gear = _gear(raw.from_gear, name="from_gear")
        to_gear = _gear(raw.to_gear, name="to_gear")
        evidence = _sha256(raw.evidence_sha256, name="evidence_sha256")
        previous = _sha256(raw.previous_event_hash, name="previous_event_hash")
        installation_id = _explicit_string(raw.installation_id, name="installation_id")
        runtime_id = _explicit_string(raw.runtime_id, name="runtime_id")
        step_id = _nonnegative_int(raw.step_id, name="step_id")
        if raw.mission_id != MISSION_ID or step_id != STEP_ID or raw.source_role != SOURCE_ROLE:
            raise ShiftHistoryGuardError("shift receipt scope/source mismatch")
        return cls(
            event_id=event_id,
            seq=seq,
            from_gear=from_gear,
            to_gear=to_gear,
            evidence_sha256=evidence,
            previous_event_hash=previous,
            installation_id=installation_id,
            runtime_id=runtime_id,
            mission_id=MISSION_ID,
            step_id=STEP_ID,
            source_role=SOURCE_ROLE,
        )

    def binding(self) -> dict[str, Any]:
        return asdict(self)

    def event_hash(self) -> str:
        return _hash_payload(self.binding())

    def lineage_key(self) -> str:
        return _hash_payload({
            "evidence_sha256": self.evidence_sha256,
            "installation_id": self.installation_id,
            "runtime_id": self.runtime_id,
            "mission_id": self.mission_id,
            "step_id": self.step_id,
        })


@dataclass(frozen=True)
class ThrashPolicy:
    window_size: int
    minimum_support: int
    enter_rate: float
    exit_rate: float
    z_value: float = 1.96

    @classmethod
    def from_value(cls, value: Any) -> "ThrashPolicy":
        if isinstance(value, cls):
            policy = value
        elif isinstance(value, Mapping):
            try:
                policy = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise ShiftHistoryGuardError("malformed thrash policy") from exc
        else:
            raise ShiftHistoryGuardError("thrash policy must be mapping or ThrashPolicy")
        window = _positive_int(policy.window_size, name="window_size")
        support = _positive_int(policy.minimum_support, name="minimum_support")
        if support > window:
            raise ShiftHistoryGuardError("minimum_support cannot exceed window_size")
        enter = _ratio(policy.enter_rate, name="enter_rate")
        exit_rate = _ratio(policy.exit_rate, name="exit_rate")
        if exit_rate >= enter:
            raise ShiftHistoryGuardError("exit_rate must be lower than enter_rate for hysteresis")
        if isinstance(policy.z_value, bool) or not isinstance(policy.z_value, (int, float)) or float(policy.z_value) <= 0:
            raise ShiftHistoryGuardError("z_value must be positive numeric")
        return cls(window, support, enter, exit_rate, float(policy.z_value))

    def fingerprint(self) -> str:
        return _hash_payload(asdict(self))


@dataclass(frozen=True)
class AppendResult:
    status: str
    event_hash: str
    head_hash: str
    accepted_count: int


@dataclass(frozen=True)
class ThrashObservation:
    window_size_requested: int
    sample_size: int
    shift_count: int
    shift_rate: float
    wilson_lower: float
    wilson_upper: float
    policy_fingerprint: str
    state_before: str
    state_after: str
    transition: str
    latest_seq: int
    ledger_head_hash: str
    sufficient_support: bool
    live_routing_authority_allowed: bool = False
    formal_mutation_allowed: bool = False
    experience_delta: int = 0
    operational_progress_delta: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _empty_registry(*, installation_id: str, runtime_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mission_id": MISSION_ID,
        "step_id": STEP_ID,
        "installation_id": installation_id,
        "runtime_id": runtime_id,
        "head_hash": ZERO_HASH,
        "latest_seq": 0,
        "events": [],
        "by_event_id": {},
        "by_lineage": {},
        "thrash_state": "CLEAR",
        "thrash_policy_fingerprint": None,
    }


def _load_registry(path: Path, *, installation_id: str, runtime_id: str) -> dict[str, Any]:
    installation_id = _explicit_string(installation_id, name="installation_id")
    runtime_id = _explicit_string(runtime_id, name="runtime_id")
    if not path.exists():
        return _empty_registry(installation_id=installation_id, runtime_id=runtime_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShiftHistoryGuardError("shift registry unreadable") from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ShiftHistoryGuardError("unsupported shift registry schema")
    if data.get("mission_id") != MISSION_ID or data.get("step_id") != STEP_ID:
        raise ShiftHistoryGuardError("shift registry mission/step mismatch")
    if data.get("installation_id") != installation_id or data.get("runtime_id") != runtime_id:
        raise ShiftHistoryGuardError("cross-installation/runtime shift registry rejected")
    if data.get("thrash_state") not in {"CLEAR", "THRASH"}:
        raise ShiftHistoryGuardError("invalid thrash state")
    if not isinstance(data.get("events"), list) or not isinstance(data.get("by_event_id"), dict) or not isinstance(data.get("by_lineage"), dict):
        raise ShiftHistoryGuardError("malformed shift registry")
    return data


def _atomic_save(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(data), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def append_shift_event(event: Any, *, registry_path: Path, installation_id: str, runtime_id: str) -> AppendResult:
    """Append one canonical G1..G6 decision observation to a durable shadow ledger.

    Identity is accepted only after exact sequence/hash-chain/scope validation.
    Same accepted binding is a duplicate NO_OP. Same event ID with another binding
    is a hard conflict. Same evidence lineage under a new ID is a lineage duplicate.
    """
    receipt = ShiftEventReceipt.from_value(event)
    if receipt.installation_id != installation_id or receipt.runtime_id != runtime_id:
        raise ShiftHistoryGuardError("receipt runtime/install does not match registry scope")
    registry = _load_registry(registry_path, installation_id=installation_id, runtime_id=runtime_id)
    event_hash = receipt.event_hash()
    existing = registry["by_event_id"].get(receipt.event_id)
    if existing is not None:
        if existing == event_hash:
            return AppendResult("DUPLICATE_NO_OP", event_hash, registry["head_hash"], len(registry["events"]))
        raise ShiftHistoryGuardError("IDENTITY_CONFLICT")
    lineage = receipt.lineage_key()
    if lineage in registry["by_lineage"]:
        return AppendResult("LINEAGE_DUPLICATE_NO_OP", event_hash, registry["head_hash"], len(registry["events"]))
    expected_seq = int(registry["latest_seq"]) + 1
    if receipt.seq != expected_seq:
        raise ShiftHistoryGuardError("non-contiguous shift sequence")
    if receipt.previous_event_hash != registry["head_hash"]:
        raise ShiftHistoryGuardError("shift hash-chain predecessor mismatch")

    event_record = receipt.binding()
    event_record["event_hash"] = event_hash
    event_record["changed_gear"] = receipt.from_gear != receipt.to_gear
    registry["events"].append(event_record)
    registry["by_event_id"][receipt.event_id] = event_hash
    registry["by_lineage"][lineage] = receipt.event_id
    registry["head_hash"] = event_hash
    registry["latest_seq"] = receipt.seq
    _atomic_save(registry_path, registry)
    return AppendResult("ACCEPTED", event_hash, event_hash, len(registry["events"]))


def _wilson_interval(successes: int, n: int, z: float) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denominator
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def evaluate_thrash(*, registry_path: Path, installation_id: str, runtime_id: str, policy: Any) -> ThrashObservation:
    """Derive anti-thrash state from accepted append-only history, never from a raw ratio.

    Entry requires the Wilson lower bound to reach the enter threshold; exit requires
    the Wilson upper bound to fall below the lower exit threshold. Between thresholds,
    state is held. Insufficient support never enters thrash and never force-exits an
    already active state. Threshold values are research policy inputs, not capability truth.
    """
    policy = ThrashPolicy.from_value(policy)
    registry = _load_registry(registry_path, installation_id=installation_id, runtime_id=runtime_id)
    events = registry["events"][-policy.window_size:]
    n = len(events)
    shifts = sum(1 for event in events if bool(event.get("changed_gear")))
    rate = shifts / n if n else 0.0
    lower, upper = _wilson_interval(shifts, n, policy.z_value)
    before = registry["thrash_state"]
    after = before
    transition = "INSUFFICIENT_SUPPORT"
    sufficient = n >= policy.minimum_support

    if sufficient:
        if before == "CLEAR" and lower >= policy.enter_rate:
            after = "THRASH"
            transition = "ENTER"
        elif before == "THRASH" and upper <= policy.exit_rate:
            after = "CLEAR"
            transition = "EXIT"
        else:
            transition = "HOLD"

    fingerprint = policy.fingerprint()
    if registry.get("thrash_policy_fingerprint") not in {None, fingerprint} and before == "THRASH":
        # A policy change must not silently clear an already active guard state.
        after = "THRASH"
        transition = "POLICY_CHANGED_HOLD"
    registry["thrash_state"] = after
    registry["thrash_policy_fingerprint"] = fingerprint
    _atomic_save(registry_path, registry)

    return ThrashObservation(
        window_size_requested=policy.window_size,
        sample_size=n,
        shift_count=shifts,
        shift_rate=round(rate, 6),
        wilson_lower=round(lower, 6),
        wilson_upper=round(upper, 6),
        policy_fingerprint=fingerprint,
        state_before=before,
        state_after=after,
        transition=transition,
        latest_seq=int(registry["latest_seq"]),
        ledger_head_hash=registry["head_hash"],
        sufficient_support=sufficient,
    )
