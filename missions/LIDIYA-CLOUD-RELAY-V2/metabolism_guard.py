from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ALLOWED_BACKUPS = {
    "RECOVERY_BASELINE": "READ_ONLY",
    "WORKING_EXCHANGE": "MUTABLE_COLLABORATION",
}
ALLOWED_DELETE_CLASSES = {
    "stage_scratch",
    "temporary_request_response",
    "duplicate_generated_artifact",
    "expired_unreferenced_ttl",
    "reproducible_superseded_intermediate",
    "duplicate_authoritative_proof",
}
ALLOWED_WORK_AREAS = {"scratch", "workbench", "tmp", "temp", "cache", "debug"}
PROTECTED_MARKERS = {
    "authorizations",
    "state",
    "governance",
    "identity",
    "identity_kernel",
    "personality",
    "approved_memory",
    "current_state",
    "handoff",
    "closure",
    "recovery_baseline",
}
SECRET_MARKERS = {
    "secret",
    "token",
    "apikey",
    "api_key",
    "password",
    "credential",
    "cookie",
    "private_key",
}


class GuardRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class Artifact:
    path: str
    artifact_class: str
    referenced: bool = False
    unique: bool = False
    reproducible: bool = False
    recovery_ok: bool = False
    human_created: bool = False
    protected: bool = False
    provenance_clear: bool = True


@dataclass(frozen=True)
class GuardResult:
    reachability: bool
    uniqueness: bool
    reproducibility: bool
    recovery: bool

    @property
    def all_pass(self) -> bool:
        return self.reachability and self.uniqueness and self.reproducibility and self.recovery


@dataclass(frozen=True)
class Decision:
    path: str
    disposition: str
    reason: str
    guards: GuardResult
    sha256: str | None = None
    size: int | None = None


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_backup_groups(groups: dict[str, str]) -> None:
    if len(groups) > 2:
        raise GuardRejected("third full backup forbidden")
    for name, mode in groups.items():
        expected = ALLOWED_BACKUPS.get(name)
        if expected is None:
            raise GuardRejected(f"unknown full backup group: {name}")
        if mode != expected:
            raise GuardRejected(f"backup mode mismatch for {name}")
    if groups.get("RECOVERY_BASELINE") != "READ_ONLY":
        raise GuardRejected("RECOVERY_BASELINE must remain READ_ONLY")


def _parts(path: str) -> tuple[str, ...]:
    p = Path(path)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise GuardRejected("unsafe relative path")
    return tuple(part.lower() for part in p.parts)


def _secret_like(parts: tuple[str, ...]) -> bool:
    joined = "/".join(parts)
    return any(marker in joined for marker in SECRET_MARKERS)


def _protected_like(parts: tuple[str, ...]) -> bool:
    return any(part in PROTECTED_MARKERS for part in parts)


def evaluate_guards(artifact: Artifact) -> GuardResult:
    return GuardResult(
        reachability=not artifact.referenced,
        uniqueness=not artifact.unique and not artifact.human_created,
        reproducibility=artifact.reproducible,
        recovery=artifact.recovery_ok,
    )


def classify(artifact: Artifact) -> Decision:
    parts = _parts(artifact.path)
    guards = evaluate_guards(artifact)
    if _secret_like(parts):
        return Decision(artifact.path, "QUARANTINE", "secret-like path", guards)
    if artifact.protected or _protected_like(parts):
        return Decision(artifact.path, "KEEP", "protected canonical material", guards)
    if not artifact.provenance_clear:
        return Decision(artifact.path, "QUARANTINE", "ambiguous provenance", guards)
    if artifact.referenced:
        return Decision(artifact.path, "KEEP", "reachable from live durable state", guards)
    if artifact.unique or artifact.human_created:
        return Decision(artifact.path, "KEEP", "unique or human-created material", guards)
    if artifact.artifact_class not in ALLOWED_DELETE_CLASSES:
        return Decision(artifact.path, "KEEP", "class outside automatic-clear allowlist", guards)
    if not artifact.reproducible:
        return Decision(artifact.path, "QUARANTINE", "artifact is not reproducible", guards)
    if not artifact.recovery_ok:
        return Decision(artifact.path, "QUARANTINE", "recovery check failed", guards)
    if parts[0] not in ALLOWED_WORK_AREAS:
        return Decision(artifact.path, "WASTE", "eligible waste outside physical auto-clear area", guards)
    return Decision(artifact.path, "DELETE_CANDIDATE", "all machine guards passed", guards)


def _safe_target(root: Path, rel_path: str) -> Path:
    root = root.resolve()
    parts = _parts(rel_path)
    candidate = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise GuardRejected("symlink target refused")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise GuardRejected("path escapes cleanup root") from exc
    return candidate


def _safe_file_fingerprint(target: Path, decision: Decision) -> tuple[str | None, int | None]:
    parts = _parts(decision.path)
    if _secret_like(parts):
        return None, None
    if not target.exists() or not target.is_file():
        return None, None
    data = target.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def snapshot(root: Path, artifacts: Iterable[Artifact]) -> dict:
    rows = []
    for artifact in sorted(artifacts, key=lambda item: item.path):
        decision = classify(artifact)
        target = _safe_target(root, artifact.path)
        sha, size = _safe_file_fingerprint(target, decision)
        rows.append(
            {
                "path": artifact.path,
                "exists": target.exists(),
                "disposition": decision.disposition,
                "sha256": sha,
                "size": size,
            }
        )
    body = {"schema_version": "1.0", "items": rows}
    body["manifest_sha256"] = canonical_sha256(body)
    return body


def cleanup_fixture(root: Path, artifacts: Iterable[Artifact], *, apply: bool = False) -> dict:
    artifacts = list(artifacts)
    before = snapshot(root, artifacts)
    decisions: list[Decision] = [classify(artifact) for artifact in artifacts]
    deleted: list[str] = []
    reclaimed_bytes = 0

    if apply:
        for decision in decisions:
            if decision.disposition != "DELETE_CANDIDATE" or not decision.guards.all_pass:
                continue
            target = _safe_target(root, decision.path)
            if not target.exists():
                continue
            if not target.is_file():
                raise GuardRejected("automatic cleanup only deletes enumerated files")
            sha, size = _safe_file_fingerprint(target, decision)
            if sha is None or size is None:
                raise GuardRejected("refuse deletion without safe fingerprint")
            target.unlink()
            deleted.append(decision.path)
            reclaimed_bytes += size

    after = snapshot(root, artifacts)
    compact = {
        "schema_version": "1.0",
        "mode": "apply" if apply else "dry-run",
        "before_manifest_sha256": before["manifest_sha256"],
        "after_manifest_sha256": after["manifest_sha256"],
        "deleted": sorted(deleted),
        "deleted_count": len(deleted),
        "reclaimed_bytes": reclaimed_bytes,
        "dispositions": {
            name: sum(decision.disposition == name for decision in decisions)
            for name in ("KEEP", "QUARANTINE", "WASTE", "DELETE_CANDIDATE")
        },
        "decisions": [
            {
                "path": decision.path,
                "disposition": decision.disposition,
                "reason": decision.reason,
                "guards": asdict(decision.guards),
            }
            for decision in sorted(decisions, key=lambda item: item.path)
        ],
        "raw_worksite_retained": False,
    }
    compact["report_sha256"] = canonical_sha256(compact)
    return compact
