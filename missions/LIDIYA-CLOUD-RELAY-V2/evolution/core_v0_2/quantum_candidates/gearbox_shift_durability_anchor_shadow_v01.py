from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

# Non-formal shadow research only. This module does not mutate MISSION_STATE,
# does not replace Gearbox v1/v2/v2.1, and does not claim LCR-C verification.

from gearbox_shift_history_shadow_v01 import (
    MISSION_ID,
    STEP_ID,
    ShiftHistoryGuardError,
    _load_registry as _load_shift_registry,
    append_shift_event,
)

ANCHOR_SCHEMA_VERSION = "0.1-shadow"
ANCHOR_AUTHORITY = "EXTERNAL_MONOTONIC_ANCHOR_SHADOW"
ZERO_HASH = "0" * 64


class DurabilityAnchorGuardError(ValueError):
    pass


def _explicit_string(value: Any, *, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise DurabilityAnchorGuardError(f"{name} must be explicit non-empty string")
    return value.strip()


def _nonnegative_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DurabilityAnchorGuardError(f"{name} must be nonnegative integer")
    return value


def _sha256(value: Any, *, name: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise DurabilityAnchorGuardError(f"{name} must be 64-hex sha256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise DurabilityAnchorGuardError(f"{name} must be 64-hex sha256") from exc
    return value.lower()


def _hash_payload(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DurabilityAnchorGuardError(f"{label} unreadable") from exc
    if not isinstance(data, dict):
        raise DurabilityAnchorGuardError(f"{label} must be object")
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


@dataclass(frozen=True)
class ExternalMonotonicAnchorReceipt:
    anchor_seq: int
    ledger_head_hash: str
    installation_id: str
    runtime_id: str
    durability_domain_id: str
    previous_anchor_hash: str
    authority_id: str = ANCHOR_AUTHORITY
    mission_id: str = MISSION_ID
    step_id: int = STEP_ID
    schema_version: str = ANCHOR_SCHEMA_VERSION

    @classmethod
    def from_value(cls, value: Any) -> "ExternalMonotonicAnchorReceipt":
        if isinstance(value, cls):
            raw = value
        elif isinstance(value, Mapping):
            try:
                raw = cls(**dict(value))
            except (TypeError, ValueError) as exc:
                raise DurabilityAnchorGuardError("malformed anchor receipt") from exc
        else:
            raise DurabilityAnchorGuardError("anchor receipt must be mapping or receipt")
        seq = _nonnegative_int(raw.anchor_seq, name="anchor_seq")
        head = _sha256(raw.ledger_head_hash, name="ledger_head_hash")
        previous = _sha256(raw.previous_anchor_hash, name="previous_anchor_hash")
        installation_id = _explicit_string(raw.installation_id, name="installation_id")
        runtime_id = _explicit_string(raw.runtime_id, name="runtime_id")
        domain_id = _explicit_string(raw.durability_domain_id, name="durability_domain_id")
        if raw.authority_id != ANCHOR_AUTHORITY:
            raise DurabilityAnchorGuardError("anchor authority mismatch")
        if raw.mission_id != MISSION_ID or raw.step_id != STEP_ID:
            raise DurabilityAnchorGuardError("anchor mission/step mismatch")
        if raw.schema_version != ANCHOR_SCHEMA_VERSION:
            raise DurabilityAnchorGuardError("anchor schema mismatch")
        if seq == 0 and head != ZERO_HASH:
            raise DurabilityAnchorGuardError("zero anchor must use zero ledger head")
        return cls(seq, head, installation_id, runtime_id, domain_id, previous)

    def binding(self) -> dict[str, Any]:
        return asdict(self)

    def anchor_hash(self) -> str:
        return _hash_payload(self.binding())


@dataclass(frozen=True)
class AnchorVerification:
    status: str
    ledger_seq: int
    anchor_seq: int
    ledger_head_hash: str
    anchor_head_hash: str
    live_routing_authority_allowed: bool = False
    formal_mutation_allowed: bool = False
    experience_delta: int = 0
    operational_progress_delta: int = 0


@dataclass(frozen=True)
class AnchoredAppendResult:
    status: str
    event_status: str
    anchor_status: str
    ledger_seq: int
    anchor_seq: int
    ledger_head_hash: str
    anchor_hash: str


def _ledger_snapshot(registry_path: Path, *, installation_id: str, runtime_id: str) -> tuple[int, str]:
    if not registry_path.exists():
        return 0, ZERO_HASH
    try:
        data = _load_shift_registry(
            registry_path,
            installation_id=installation_id,
            runtime_id=runtime_id,
        )
    except ShiftHistoryGuardError as exc:
        raise DurabilityAnchorGuardError(f"shift registry integrity failure: {exc}") from exc
    seq = _nonnegative_int(data.get("latest_seq"), name="ledger latest_seq")
    head = _sha256(data.get("head_hash"), name="ledger head_hash")
    return seq, head


def _anchor_file_payload(receipt: ExternalMonotonicAnchorReceipt) -> dict[str, Any]:
    payload = receipt.binding()
    payload["anchor_hash"] = receipt.anchor_hash()
    return payload


def _load_anchor(anchor_path: Path, *, installation_id: str, runtime_id: str, durability_domain_id: str) -> ExternalMonotonicAnchorReceipt:
    data = _read_json(anchor_path, label="external anchor")
    raw = {key: data.get(key) for key in (
        "anchor_seq", "ledger_head_hash", "installation_id", "runtime_id",
        "durability_domain_id", "previous_anchor_hash", "authority_id",
        "mission_id", "step_id", "schema_version",
    )}
    receipt = ExternalMonotonicAnchorReceipt.from_value(raw)
    if receipt.installation_id != installation_id or receipt.runtime_id != runtime_id:
        raise DurabilityAnchorGuardError("anchor scope mismatch")
    if receipt.durability_domain_id != durability_domain_id:
        raise DurabilityAnchorGuardError("anchor durability domain mismatch")
    if data.get("anchor_hash") != receipt.anchor_hash():
        raise DurabilityAnchorGuardError("anchor hash mismatch")
    return receipt


def initialize_empty_anchor(*, registry_path: Path, anchor_path: Path,
                            installation_id: str, runtime_id: str,
                            durability_domain_id: str) -> ExternalMonotonicAnchorReceipt:
    """Bootstrap only when both ledger and anchor are empty/nonexistent.

    A nonempty ledger cannot be retroactively declared trustworthy by creating an
    anchor beside it; that requires an external trusted migration/verification step.
    """
    installation_id = _explicit_string(installation_id, name="installation_id")
    runtime_id = _explicit_string(runtime_id, name="runtime_id")
    durability_domain_id = _explicit_string(durability_domain_id, name="durability_domain_id")
    if anchor_path.exists():
        raise DurabilityAnchorGuardError("anchor already exists")
    ledger_seq, ledger_head = _ledger_snapshot(registry_path, installation_id=installation_id, runtime_id=runtime_id)
    if ledger_seq != 0 or ledger_head != ZERO_HASH:
        raise DurabilityAnchorGuardError("cannot bootstrap anchor from nonempty ledger")
    receipt = ExternalMonotonicAnchorReceipt(
        anchor_seq=0,
        ledger_head_hash=ZERO_HASH,
        installation_id=installation_id,
        runtime_id=runtime_id,
        durability_domain_id=durability_domain_id,
        previous_anchor_hash=ZERO_HASH,
    )
    _atomic_save(anchor_path, _anchor_file_payload(receipt))
    return receipt


def verify_anchor(*, registry_path: Path, anchor_path: Path,
                  installation_id: str, runtime_id: str,
                  durability_domain_id: str) -> AnchorVerification:
    installation_id = _explicit_string(installation_id, name="installation_id")
    runtime_id = _explicit_string(runtime_id, name="runtime_id")
    durability_domain_id = _explicit_string(durability_domain_id, name="durability_domain_id")
    anchor = _load_anchor(anchor_path, installation_id=installation_id, runtime_id=runtime_id,
                          durability_domain_id=durability_domain_id)
    ledger_seq, ledger_head = _ledger_snapshot(registry_path, installation_id=installation_id, runtime_id=runtime_id)
    if ledger_seq < anchor.anchor_seq:
        status = "LEDGER_ROLLBACK_DETECTED"
    elif ledger_seq > anchor.anchor_seq:
        status = "UNANCHORED_LEDGER_ADVANCE"
    elif ledger_head != anchor.ledger_head_hash:
        status = "LEDGER_ANCHOR_FORK_DETECTED"
    else:
        status = "ANCHOR_MATCH"
    return AnchorVerification(status, ledger_seq, anchor.anchor_seq, ledger_head, anchor.ledger_head_hash)


@contextmanager
def exclusive_writer_lock(lock_path: Path, *, owner_token: str | None = None) -> Iterator[str]:
    """Cross-process fail-closed lock using atomic directory creation.

    There is deliberately no automatic stale-lock stealing. Recovery of an abandoned
    lock requires an external operator/recovery authority so two writers cannot both
    decide they own the same shift ledger.
    """
    token = owner_token or uuid.uuid4().hex
    token = _explicit_string(token, name="owner_token")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(lock_path)
    except FileExistsError as exc:
        raise DurabilityAnchorGuardError("WRITER_LOCK_HELD") from exc
    owner_path = lock_path / "owner.json"
    try:
        _atomic_save(owner_path, {"owner_token": token})
        yield token
    finally:
        try:
            owner = _read_json(owner_path, label="writer lock owner")
            if owner.get("owner_token") != token:
                raise DurabilityAnchorGuardError("WRITER_LOCK_OWNERSHIP_LOST")
            owner_path.unlink()
            lock_path.rmdir()
        except FileNotFoundError:
            raise DurabilityAnchorGuardError("WRITER_LOCK_DISAPPEARED")


def append_shift_event_anchored(event: Any, *, registry_path: Path, anchor_path: Path,
                                lock_path: Path, installation_id: str, runtime_id: str,
                                durability_domain_id: str) -> AnchoredAppendResult:
    """Serialize one append and advance the external anchor only after ledger acceptance.

    If a crash occurs after the ledger is saved but before the anchor advances, the
    next call fails closed as UNANCHORED_LEDGER_ADVANCE. This shadow module never
    auto-reconciles that state because doing so could bless an untrusted fork.
    """
    with exclusive_writer_lock(lock_path):
        before = verify_anchor(
            registry_path=registry_path, anchor_path=anchor_path,
            installation_id=installation_id, runtime_id=runtime_id,
            durability_domain_id=durability_domain_id,
        )
        if before.status != "ANCHOR_MATCH":
            raise DurabilityAnchorGuardError(before.status)
        previous_anchor = _load_anchor(
            anchor_path, installation_id=installation_id, runtime_id=runtime_id,
            durability_domain_id=durability_domain_id,
        )
        try:
            appended = append_shift_event(
                event, registry_path=registry_path,
                installation_id=installation_id, runtime_id=runtime_id,
            )
        except ShiftHistoryGuardError as exc:
            raise DurabilityAnchorGuardError(str(exc)) from exc
        if appended.status == "ACCEPTED":
            ledger_seq, ledger_head = _ledger_snapshot(
                registry_path, installation_id=installation_id, runtime_id=runtime_id,
            )
            if ledger_seq != previous_anchor.anchor_seq + 1:
                raise DurabilityAnchorGuardError("unexpected ledger sequence after accepted append")
            next_anchor = ExternalMonotonicAnchorReceipt(
                anchor_seq=ledger_seq,
                ledger_head_hash=ledger_head,
                installation_id=installation_id,
                runtime_id=runtime_id,
                durability_domain_id=durability_domain_id,
                previous_anchor_hash=previous_anchor.anchor_hash(),
            )
            _atomic_save(anchor_path, _anchor_file_payload(next_anchor))
        final_anchor = _load_anchor(
            anchor_path, installation_id=installation_id, runtime_id=runtime_id,
            durability_domain_id=durability_domain_id,
        )
        final = verify_anchor(
            registry_path=registry_path, anchor_path=anchor_path,
            installation_id=installation_id, runtime_id=runtime_id,
            durability_domain_id=durability_domain_id,
        )
        if final.status != "ANCHOR_MATCH":
            raise DurabilityAnchorGuardError(final.status)
        return AnchoredAppendResult(
            status="ACCEPTED_ANCHORED" if appended.status == "ACCEPTED" else "NO_OP_ANCHOR_UNCHANGED",
            event_status=appended.status,
            anchor_status=final.status,
            ledger_seq=final.ledger_seq,
            anchor_seq=final.anchor_seq,
            ledger_head_hash=final.ledger_head_hash,
            anchor_hash=final_anchor.anchor_hash(),
        )
