from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

UTC = timezone.utc


class RelayStateError(RuntimeError):
    pass


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "IDLE": {"COORDINATING"},
    "COORDINATING": {"READY_FOR_BUILDER", "PROJECT_DONE", "HUMAN_GATE"},
    "READY_FOR_BUILDER": {"BUILDING", "HUMAN_GATE"},
    "BUILDING": {"READY_FOR_VERIFY", "HUMAN_GATE"},
    "READY_FOR_VERIFY": {"VERIFYING", "HUMAN_GATE"},
    "VERIFYING": {"READY_FOR_BUILDER", "STEP_DONE", "HUMAN_GATE"},
    "STEP_DONE": {"COORDINATING", "PROJECT_DONE", "HUMAN_GATE"},
    "PROJECT_DONE": {"METABOLIZE"},
    "METABOLIZE": {"IDLE", "COORDINATING", "HUMAN_GATE"},
    "HUMAN_GATE": {"IDLE", "COORDINATING", "READY_FOR_BUILDER"},
}

ROLE_FOR_STATUS: dict[str, str] = {
    "IDLE": "LCR-A",
    "COORDINATING": "LCR-A",
    "READY_FOR_BUILDER": "LCR-B",
    "BUILDING": "LCR-B",
    "READY_FOR_VERIFY": "LCR-C",
    "VERIFYING": "LCR-C",
    "STEP_DONE": "LCR-A",
    "PROJECT_DONE": "LCR-A",
    "METABOLIZE": "LCR-A",
    "HUMAN_GATE": "HUMAN",
}


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def transition(state: dict[str, Any], new_status: str) -> dict[str, Any]:
    current = state["status"]
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise RelayStateError(f"invalid transition: {current} -> {new_status}")
    updated = dict(state)
    updated["status"] = new_status
    updated["current_role"] = ROLE_FOR_STATUS[new_status]
    updated["next_role"] = ROLE_FOR_STATUS[new_status]
    return updated


def lease_active(state: dict[str, Any], at: datetime | None = None) -> bool:
    lease = state.get("lease")
    if not lease:
        return False
    at = at or now_utc()
    return parse_time(lease["expires_at"]) > at


def claim(
    state: dict[str, Any],
    role: str,
    owner: str,
    ttl_seconds: int = 900,
    at: datetime | None = None,
) -> dict[str, Any]:
    at = at or now_utc()
    expected = ROLE_FOR_STATUS.get(state["status"])
    if expected != role:
        raise RelayStateError(f"role {role} cannot claim status {state['status']} (expected {expected})")

    lease = state.get("lease")
    if lease and parse_time(lease["expires_at"]) > at and lease["owner"] != owner:
        raise RelayStateError(f"active lease owned by {lease['owner']}")

    updated = dict(state)
    updated["lease"] = {
        "role": role,
        "owner": owner,
        "claimed_at": at.isoformat(),
        "expires_at": (at + timedelta(seconds=ttl_seconds)).isoformat(),
    }
    return updated


def clear_lease(state: dict[str, Any], owner: str | None = None) -> dict[str, Any]:
    lease = state.get("lease")
    if owner and lease and lease.get("owner") != owner:
        raise RelayStateError("cannot clear another worker's active lease")
    updated = dict(state)
    updated["lease"] = None
    return updated


def set_pending_packet(state: dict[str, Any], packet_path: str) -> dict[str, Any]:
    """Point at an unconsumed outbound packet without marking it consumed."""
    if not packet_path:
        raise RelayStateError("pending packet path is required")
    updated = dict(state)
    updated["pending_packet"] = packet_path
    return updated


def packet(
    *,
    state: dict[str, Any],
    run_id: str,
    source_role: str,
    target_role: str,
    status: str,
    task: str,
    acceptance: list[str],
    evidence: list[dict[str, Any]] | None = None,
    result: str | None = None,
    lesson: str | None = None,
    disposition: str = "candidate",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": state["schema_version"],
        "mission_id": state["mission_id"],
        "run_id": run_id,
        "step_id": state["step_id"],
        "attempt": state["attempt"],
        "source_role": source_role,
        "target_role": target_role,
        "status": status,
        "parent_packet_sha256": state.get("last_packet_sha256"),
        "created_at": now_utc().isoformat(),
        "lease_owner": (state.get("lease") or {}).get("owner"),
        "lease_expires_at": (state.get("lease") or {}).get("expires_at"),
        "task": task,
        "acceptance": acceptance,
        "candidate_ref": state.get("candidate_ref"),
        "evidence": evidence or [],
        "result": result,
        "lesson": lesson,
        "disposition": disposition,
    }
    payload["packet_sha256"] = sha256_json(payload)
    return payload


def consume_once(state: dict[str, Any], packet_value: dict[str, Any]) -> dict[str, Any]:
    packet_sha = packet_value.get("packet_sha256")
    if not packet_sha:
        raise RelayStateError("packet missing packet_sha256")

    expected = dict(packet_value)
    expected.pop("packet_sha256")
    if sha256_json(expected) != packet_sha:
        raise RelayStateError("packet hash mismatch")

    if state.get("last_packet_sha256") == packet_sha:
        raise RelayStateError("duplicate packet consumption")

    updated = dict(state)
    updated["last_packet_sha256"] = packet_sha
    return updated


def advance_step(state: dict[str, Any]) -> dict[str, Any]:
    updated = dict(state)
    updated["step_id"] = int(updated.get("step_id", 0)) + 1
    updated["attempt"] = 0
    return updated


def retry_step(state: dict[str, Any]) -> dict[str, Any]:
    updated = dict(state)
    updated["attempt"] = int(updated.get("attempt", 0)) + 1
    return updated
