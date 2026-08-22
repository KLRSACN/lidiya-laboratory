from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

SCHEMA = "1.0-shadow"
OPERATIONAL_METADATA_FIELDS = frozenset({
    "provider_id", "provider_head_sequence", "provider_receipt_hash",
    "signer_role", "signer_epoch", "trust_snapshot_id", "key_fingerprint_sha256",
    "clock_epoch", "clock_sequence", "clock_receipt_hash", "checkpoint_id",
    "signature_verified", "retry_count", "backoff_count", "recovery_count",
    "recovery_duration_ms", "root_reestablishment_count", "secretary_level",
    "context_load_ratio", "tool_failure_ratio", "stale_pointer_ratio",
    "durable_progress_age_ratio", "storage_pressure_ratio", "continuity_anchor_health",
})
FORBIDDEN_COGNITIVE_SINKS = frozenset({
    "accepted_experience_ids", "appraisal", "drive", "exploration", "preference",
    "personality", "p_base", "trauma", "relief", "competence", "motivation",
})

@dataclass(frozen=True)
class LearningProjection:
    accepted_experience_ids: tuple[str, ...] = ()
    appraisal: tuple[tuple[str, float], ...] = ()
    drive: tuple[tuple[str, float], ...] = ()
    exploration: tuple[tuple[str, float], ...] = ()
    preference: tuple[tuple[str, float], ...] = ()
    personality: tuple[tuple[str, float], ...] = ()
    p_base: str = "READ_ONLY_UNCHANGED"
    trauma: tuple[str, ...] = ()
    relief: tuple[str, ...] = ()
    competence: tuple[tuple[str, float], ...] = ()
    motivation: tuple[tuple[str, float], ...] = ()

    def bytes_projection(self) -> tuple[Any, ...]:
        return tuple(asdict(self).items())

@dataclass(frozen=True)
class OperationalMetadataProjection:
    fields: tuple[tuple[str, Any], ...]
    learning: LearningProjection


def project_operational_metadata_shadow(metadata: Mapping[str, Any], *, learning: LearningProjection | None = None) -> OperationalMetadataProjection:
    """Project recovery/security metadata into an operational-only namespace.

    Closed-world: unknown fields fail closed. The returned learning object is passed
    through by identity/value and is never derived from metadata. A separate,
    provenance-bound verified Experience pipeline is required to change learning.
    """
    if not isinstance(metadata, Mapping):
        raise ValueError("metadata mapping required")
    unknown = set(metadata) - OPERATIONAL_METADATA_FIELDS
    if unknown:
        raise ValueError(f"unknown recovery metadata fields: {sorted(unknown)}")
    if set(metadata) & FORBIDDEN_COGNITIVE_SINKS:
        raise ValueError("cognitive sink injection forbidden")
    base = learning or LearningProjection()
    return OperationalMetadataProjection(tuple(sorted(metadata.items())), base)


def assert_no_metadata_to_learning_path(before: LearningProjection, after: OperationalMetadataProjection) -> None:
    if after.learning.bytes_projection() != before.bytes_projection():
        raise ValueError("recovery metadata reached cognitive/personality sink")


def dataflow_boundaries() -> dict[str, object]:
    return {
        "closed_world_operational_metadata": True,
        "separate_verified_experience_required_for_learning": True,
        "experience_delta": 0,
        "appraisal_delta": 0,
        "drive_delta": 0,
        "exploration_delta": 0,
        "preference_delta": 0,
        "personality_delta": 0,
        "p_base_mutation": False,
        "trauma_relief_delta": 0,
        "competence_motivation_delta": 0,
        "formal_mutation_allowed": False,
    }
