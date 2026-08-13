from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Dict, List, Optional, Tuple

from .memory_model import MemoryRecord


@dataclass(frozen=True)
class StoreCommit:
    version: int
    memory_id: str
    memory_fingerprint: str
    snapshot_hash: str
    deduplicated: bool


class VersionedAffectiveStore:
    """Shadow-only append store. It has no filesystem/network/live-core side effects."""

    def __init__(self) -> None:
        self._history: Dict[str, List[MemoryRecord]] = {}
        self._commits: List[StoreCommit] = []

    @property
    def version(self) -> int:
        return len(self._commits)

    def latest(self, memory_id: str) -> Optional[MemoryRecord]:
        versions = self._history.get(memory_id)
        return versions[-1] if versions else None

    def history(self, memory_id: str) -> Tuple[MemoryRecord, ...]:
        return tuple(self._history.get(memory_id, ()))

    def append(self, record: MemoryRecord) -> StoreCommit:
        current = self.latest(record.memory_id)
        if current is not None and current.fingerprint() == record.fingerprint():
            return StoreCommit(
                version=self.version,
                memory_id=record.memory_id,
                memory_fingerprint=record.fingerprint(),
                snapshot_hash=self.snapshot_hash(),
                deduplicated=True,
            )
        self._history.setdefault(record.memory_id, []).append(record)
        commit = StoreCommit(
            version=self.version + 1,
            memory_id=record.memory_id,
            memory_fingerprint=record.fingerprint(),
            snapshot_hash="",
            deduplicated=False,
        )
        self._commits.append(commit)
        final = StoreCommit(
            version=commit.version,
            memory_id=commit.memory_id,
            memory_fingerprint=commit.memory_fingerprint,
            snapshot_hash=self.snapshot_hash(),
            deduplicated=False,
        )
        self._commits[-1] = final
        return final

    def delete(self, memory_id: str) -> None:
        raise RuntimeError("shadow affective store is append-only; deletion requires a separate retention/quarantine workflow")

    def snapshot_payload(self) -> dict:
        latest = {memory_id: versions[-1].canonical_payload() for memory_id, versions in sorted(self._history.items())}
        return {
            "mode": "SHADOW_ONLY",
            "store_version": self.version,
            "records": latest,
            "revision_counts": {memory_id: len(versions) for memory_id, versions in sorted(self._history.items())},
        }

    def snapshot_hash(self) -> str:
        raw = json.dumps(self.snapshot_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(raw.encode("utf-8")).hexdigest()

    def commits(self) -> Tuple[StoreCommit, ...]:
        return tuple(self._commits)
