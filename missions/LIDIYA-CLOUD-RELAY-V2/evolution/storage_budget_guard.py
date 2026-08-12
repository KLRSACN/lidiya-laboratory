from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

CEILING_BYTES = 1_000_000_000_000
COMPACT_RATIO = 0.70
STOP_CHECKPOINT_RATIO = 0.85
HUMAN_GATE_RATIO = 0.95
ALLOWED_FULL_BACKUPS = ("RECOVERY_BASELINE", "WORKING_EXCHANGE")

class StorageGuardError(ValueError):
    pass

@dataclass(frozen=True)
class StorageDecision:
    action: str
    projected_bytes: int
    projected_ratio: float
    allow_write: bool
    human_gate: bool
    reason: str
    def to_dict(self) -> dict:
        return asdict(self)

def validate_backup_groups(groups: Iterable[str]) -> None:
    groups = tuple(groups)
    if len(groups) > 2:
        raise StorageGuardError("third full backup forbidden")
    if len(set(groups)) != len(groups):
        raise StorageGuardError("duplicate full backup group")
    if any(group not in ALLOWED_FULL_BACKUPS for group in groups):
        raise StorageGuardError("unknown full backup group")

def validate_base_weight_admission(*, content_sha256: str, existing_hashes: Iterable[str], required_format: str | None, manifested_reason: str | None) -> None:
    if not isinstance(content_sha256, str) or len(content_sha256) != 64:
        raise StorageGuardError("content-addressed SHA-256 required")
    if content_sha256 in set(existing_hashes) and (not required_format or not manifested_reason):
        raise StorageGuardError("duplicate base weight rejected without required-format manifest justification")

def evaluate_write(*, known_used_bytes: int, reserved_bytes: int, proposed_size_bytes: int | None, large_write: bool = False) -> StorageDecision:
    for name, value in (("known_used_bytes", known_used_bytes), ("reserved_bytes", reserved_bytes)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise StorageGuardError(f"{name} must be non-negative integer")
    if proposed_size_bytes is None:
        if large_write:
            raise StorageGuardError("unknown-size large artifact rejected before write")
        proposed_size_bytes = 0
    if isinstance(proposed_size_bytes, bool) or not isinstance(proposed_size_bytes, int) or proposed_size_bytes < 0:
        raise StorageGuardError("proposed_size_bytes must be non-negative integer or None")
    projected = known_used_bytes + reserved_bytes + proposed_size_bytes
    ratio = projected / CEILING_BYTES
    if projected > CEILING_BYTES or ratio >= 1.0:
        return StorageDecision("HARD_REJECT", projected, ratio, False, False, "1 TB hard ceiling reached/exceeded")
    if ratio >= HUMAN_GATE_RATIO and large_write:
        return StorageDecision("FREEZE_LARGE_WRITE", projected, ratio, False, True, ">=95% requires HUMAN_GATE for large write")
    if ratio >= STOP_CHECKPOINT_RATIO and large_write:
        return StorageDecision("STOP_NEW_LARGE_CHECKPOINT", projected, ratio, False, False, ">=85% stops new large checkpoints")
    if ratio >= COMPACT_RATIO:
        return StorageDecision("ALLOW_WITH_COMPACTION", projected, ratio, True, False, ">=70% compact waste before further growth")
    return StorageDecision("ALLOW", projected, ratio, True, False, "within budget")
