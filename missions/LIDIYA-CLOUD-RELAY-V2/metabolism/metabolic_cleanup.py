from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

PROTECTED_PARTS = {
    "authorizations",
    "state",
    "governance",
    "identity",
    "identity_kernel",
    "approved_memory",
    "current_state",
    "handoff",
    "closure",
}
SECRET_MARKERS = (
    "secret",
    "token",
    "apikey",
    "api_key",
    "password",
    "credential",
    "cookie",
    "private_key",
)
ALLOWED_TOPS = {"scratch", "workbench", "tmp", "temp", "cache", "debug"}


class CleanupRefused(RuntimeError):
    pass


@dataclass
class Decision:
    path: str
    disposition: str
    reason: str
    sha256: str | None = None
    size: int | None = None


def _norm_rel(root: Path, path: Path) -> Path:
    root = root.resolve()
    candidate = path if path.is_absolute() else root / path
    try:
        rel_parts = candidate.relative_to(root).parts
    except ValueError as exc:
        raise CleanupRefused("path outside cleanup root") from exc

    current = root
    for part in rel_parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise CleanupRefused("symlink path refused")

    resolved = candidate.resolve(strict=False)
    try:
        return resolved.relative_to(root)
    except ValueError as exc:
        raise CleanupRefused("resolved path escapes cleanup root") from exc


def _secret_like(rel: Path) -> bool:
    normalized = "/".join(rel.parts).lower()
    return any(marker in normalized for marker in SECRET_MARKERS)


def classify(root: Path, path: Path) -> Decision:
    rel = _norm_rel(root, path)
    parts_lower = {part.lower() for part in rel.parts}
    if not rel.parts:
        return Decision(".", "PROTECTED", "cleanup root itself")
    if _secret_like(rel):
        return Decision(rel.as_posix(), "PROTECTED", "secret-like path")
    if parts_lower & PROTECTED_PARTS:
        return Decision(rel.as_posix(), "PROTECTED", "protected canonical path segment")
    if rel.parts[0].lower() not in ALLOWED_TOPS:
        return Decision(rel.as_posix(), "RETAIN", "outside disposable allowlist")

    target = root.resolve() / rel
    if not target.exists():
        return Decision(rel.as_posix(), "RETAIN", "path does not exist")
    if target.is_dir():
        return Decision(rel.as_posix(), "DISPOSABLE", "allowlisted disposable directory")

    data = target.read_bytes()
    return Decision(
        rel.as_posix(),
        "DISPOSABLE",
        "allowlisted disposable file",
        hashlib.sha256(data).hexdigest(),
        len(data),
    )


def plan(root: Path, paths: Iterable[Path]) -> list[Decision]:
    return [classify(root, path) for path in paths]


def apply(root: Path, decisions: Iterable[Decision]) -> list[Decision]:
    root = root.resolve()
    targets: list[tuple[int, Path, Decision]] = []
    for decision in decisions:
        if decision.disposition != "DISPOSABLE":
            continue
        rel = _norm_rel(root, Path(decision.path))
        targets.append((len(rel.parts), root / rel, decision))

    applied: list[Decision] = []
    for _, target, decision in sorted(targets, key=lambda item: item[0], reverse=True):
        if not target.exists():
            applied.append(
                Decision(
                    decision.path,
                    "DISPOSABLE",
                    "already absent",
                    decision.sha256,
                    decision.size,
                )
            )
            continue
        if target.is_dir():
            try:
                target.rmdir()
            except OSError as exc:
                raise CleanupRefused(
                    f"directory not empty or unsafe: {decision.path}"
                ) from exc
        else:
            target.unlink()
        applied.append(decision)
    return applied


def manifest(decisions: list[Decision], *, mode: str) -> dict:
    return {
        "schema_version": "1.0",
        "mode": mode,
        "decisions": [asdict(decision) for decision in decisions],
        "summary": {
            "protected": sum(d.disposition == "PROTECTED" for d in decisions),
            "retained": sum(d.disposition == "RETAIN" for d in decisions),
            "disposable": sum(d.disposition == "DISPOSABLE" for d in decisions),
        },
        "content_values_retained": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed LCR metabolic cleanup.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    root = Path(args.root)
    decisions = plan(root, [Path(path) for path in args.paths])
    if args.apply:
        apply(root, decisions)
    Path(args.manifest).write_text(
        json.dumps(
            manifest(decisions, mode="apply" if args.apply else "dry-run"),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
