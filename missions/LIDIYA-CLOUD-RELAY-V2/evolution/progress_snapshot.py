from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

REQUIRED_FIELDS = ("mission_status","current_role","verified_evidence","blocker","storage_ledger","package_radar_delta","evolution_suggestions","self_review","next_autonomous_action")
CANONICAL_NAME = "EVOLUTION_PROGRESS.json"

class ProgressGuardError(ValueError):
    pass

def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def validate_progress_path(path: Path) -> None:
    if path.name != CANONICAL_NAME or path.parent.name != "state":
        raise ProgressGuardError("only state/EVOLUTION_PROGRESS.json is canonical")

def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ProgressGuardError("saved_at must be ISO-8601 string")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ProgressGuardError("saved_at must be ISO-8601") from exc

def normalize_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(snapshot)
    missing = [field for field in REQUIRED_FIELDS if field not in out]
    if missing:
        raise ProgressGuardError("missing required fields: " + ",".join(missing))
    if "mission_id" not in out or "step_id" not in out or "saved_at" not in out:
        raise ProgressGuardError("mission_id, step_id, saved_at required")
    if isinstance(out["step_id"], bool) or not isinstance(out["step_id"], int) or out["step_id"] < 0:
        raise ProgressGuardError("step_id must be non-negative integer")
    _parse_time(out["saved_at"])
    normalized = json.loads(canonical_json(out))
    normalized["snapshot_sha256"] = canonical_sha256(normalized)
    return normalized

def reject_stale(existing: Mapping[str, Any] | None, candidate: Mapping[str, Any]) -> None:
    if not existing or existing.get("mission_id") != candidate.get("mission_id"):
        return
    old_step, new_step = existing.get("step_id"), candidate.get("step_id")
    if isinstance(old_step, int) and isinstance(new_step, int):
        if new_step < old_step:
            raise ProgressGuardError("stale progress step refused")
        if new_step == old_step and _parse_time(candidate.get("saved_at")) < _parse_time(existing.get("saved_at")):
            raise ProgressGuardError("stale progress timestamp refused")

def write_progress_snapshot(path: Path, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validate_progress_path(path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    reject_stale(existing, snapshot)
    normalized = normalize_snapshot(snapshot)
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    return normalized
