"""Continuous-control and bounded external self-metabolism guards for LCR-METABOLISM-0003.

This module intentionally operates only on explicit durable/external metadata supplied
by callers. It never attempts to inspect, mutate, or erase model/system hidden state.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

FORMAL_SLOTS = ("LCR-A", "LCR-B", "LCR-C")
PROTECTED_CONTROL_FIELDS = (
    "mission_id",
    "status",
    "step_id",
    "current_role",
    "pending_packet",
    "pending_packet_sha256",
    "lease",
)
COMPACT_RETAIN_FIELDS = (
    "mission_id",
    "status",
    "step_id",
    "current_role",
    "latest_verified_evidence",
    "pending_packet",
    "pending_packet_sha256",
    "lease",
    "rollback_anchor",
    "blocker",
    "root_cause_lesson",
)
EXCLUDED_TRANSIENT_FIELDS = frozenset(
    {
        "raw_chat",
        "raw_messages",
        "raw_logs",
        "logs",
        "duplicate_self_reports",
        "self_reports",
        "stale_panels",
        "status_panel_cache",
    }
)
ALLOWLISTED_SELF_CLEAR_KINDS = frozenset(
    {
        "relay_scratch",
        "workspace_scratch",
        "relay_cache",
        "workspace_cache",
        "debug_trace",
        "duplicate_summary",
        "expired_relay_metadata",
    }
)
PROTECTED_KINDS = frozenset(
    {
        "protected_evidence",
        "rollback_anchor",
        "stable",
        "recovery_baseline",
        "durable_referenced",
        "unique_human_work",
        "unreproducible",
        "secret",
        "credential",
        "identity",
        "personality",
        "governance",
        "ambiguous_provenance",
        "hidden_model_state",
        "system_state",
        "raw_user_chat",
    }
)
SECRET_MARKERS = ("secret", "credential", "token", "apikey", "api_key", "password", "private_key")


class ControlGuardError(ValueError):
    """Fail-closed guard violation."""


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def validate_formal_roster(roster: Mapping[str, Any]) -> bool:
    """Require exactly three formal slots and no fourth slot."""
    if set(roster.keys()) != set(FORMAL_SLOTS) or len(roster) != 3:
        raise ControlGuardError("formal roster must contain exactly LCR-A/LCR-B/LCR-C")
    return True


def durable_state_fingerprint(state: Mapping[str, Any]) -> str:
    """Fingerprint only mission-control fields needed to bind a takeover."""
    material = {field: copy.deepcopy(state.get(field)) for field in PROTECTED_CONTROL_FIELDS}
    return digest(material)


def normalize_registry(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    validate_formal_roster(registry)
    out: dict[str, dict[str, Any]] = {}
    for slot in FORMAL_SLOTS:
        value = registry[slot]
        if isinstance(value, str):
            out[slot] = {"worker_id": value, "generation": 0}
        elif isinstance(value, Mapping):
            worker_id = value.get("worker_id")
            generation = value.get("generation", 0)
            if not worker_id or not isinstance(generation, int) or generation < 0:
                raise ControlGuardError("invalid registry entry")
            out[slot] = {"worker_id": str(worker_id), "generation": generation}
        else:
            raise ControlGuardError("invalid registry entry")
    return out


def same_slot_durable_handoff(
    registry: Mapping[str, Any],
    state: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Replace one worker only with an explicitly authorized, state-bound handoff."""
    current = normalize_registry(registry)
    slot = handoff.get("slot")
    if slot not in FORMAL_SLOTS:
        raise ControlGuardError("slot 4 rejected")
    entry = current[slot]
    expected_generation = entry["generation"] + 1
    expected_fingerprint = durable_state_fingerprint(state)
    required = {
        "from": entry["worker_id"],
        "slot": slot,
        "authorized": True,
        "generation": expected_generation,
        "state_fingerprint": expected_fingerprint,
    }
    for key, expected in required.items():
        if handoff.get(key) != expected:
            raise ControlGuardError("valid SAME_SLOT_DURABLE_HANDOFF required")
    new_worker = handoff.get("to")
    if not new_worker or new_worker == entry["worker_id"]:
        raise ControlGuardError("replacement worker required")
    result = copy.deepcopy(current)
    result[slot] = {"worker_id": str(new_worker), "generation": expected_generation}
    return result


def authorize_worker_action(registry: Mapping[str, Any], slot: str, worker_id: str, generation: int) -> bool:
    """Reject former/stale workers after a takeover."""
    current = normalize_registry(registry)
    if slot not in FORMAL_SLOTS:
        raise ControlGuardError("invalid slot")
    entry = current[slot]
    if entry["worker_id"] != worker_id or entry["generation"] != generation:
        raise ControlGuardError("stale or unauthorized worker action rejected")
    return True


def record_control_input(state: Mapping[str, Any], control_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Record owner/user/collaborator input as metadata without resetting mission state.

    The raw body is fingerprinted but never persisted in the durable record.
    """
    before = {field: copy.deepcopy(state.get(field)) for field in PROTECTED_CONTROL_FIELDS}
    out = copy.deepcopy(dict(state))
    raw_body = control_input.get("body", control_input.get("raw_body", ""))
    metadata = {
        "source": str(control_input.get("source", "unknown")),
        "kind": str(control_input.get("kind", "control_input")),
        "received_at": control_input.get("received_at"),
        "body_sha256": hashlib.sha256(str(raw_body).encode("utf-8")).hexdigest(),
    }
    durable_inputs = list(out.get("control_inputs", []))
    durable_inputs.append(metadata)
    out["control_inputs"] = durable_inputs
    after = {field: copy.deepcopy(out.get(field)) for field in PROTECTED_CONTROL_FIELDS}
    if before != after:
        raise ControlGuardError("control input attempted to reset durable mission")
    return out, metadata


def compact_control_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    """Create deterministic durable control truth while dropping transient worksite noise."""
    compact: dict[str, Any] = {}
    for field in COMPACT_RETAIN_FIELDS:
        if field in state:
            compact[field] = copy.deepcopy(state[field])
    for forbidden in EXCLUDED_TRANSIENT_FIELDS:
        compact.pop(forbidden, None)
    compact["snapshot_sha256"] = digest(compact)
    return compact


def classify_external_artifact(item: Mapping[str, Any]) -> str:
    """Fail-closed external metadata classifier; returns SELF_CLEARABLE or QUARANTINE."""
    kind = str(item.get("kind", "")).strip().lower()
    path = str(item.get("path", "")).strip().lower()
    provenance = str(item.get("provenance", "")).strip().lower()

    if kind in PROTECTED_KINDS:
        return "QUARANTINE"
    if not provenance or provenance in {"ambiguous", "unknown", "conflicting"}:
        return "QUARANTINE"
    if any(marker in path for marker in SECRET_MARKERS):
        return "QUARANTINE"
    if item.get("referenced") or item.get("unique") or item.get("human_created"):
        return "QUARANTINE"
    if item.get("reproducible") is not True or item.get("recovery_ok") is not True:
        return "QUARANTINE"
    if kind not in ALLOWLISTED_SELF_CLEAR_KINDS:
        return "QUARANTINE"
    return "SELF_CLEARABLE"


def compact_restart_handoff(state: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic compact material sufficient to restore control routing."""
    normalized = normalize_registry(registry)
    snapshot = compact_control_snapshot(state)
    result = {
        "formal_slots": list(FORMAL_SLOTS),
        "registry": normalized,
        "control_snapshot": snapshot,
        "state_fingerprint": durable_state_fingerprint(state),
    }
    result["handoff_sha256"] = digest(result)
    return result
