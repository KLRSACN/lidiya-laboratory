from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import re

MISSION_ID = "LCR-EVOLUTION-0005"
STEP_ID = 9
SCHEMA_VERSION = "0.1-shadow"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BLOB_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_SUITES = {"SIGNED_PRESSURE_CHRONICITY_NEUTRALITY_10000_AB", "RECOVERY_METADATA_END_TO_END_DATAFLOW_EXCLUSION"}

class LearningIsolationEvidenceGuardError(ValueError):
    pass


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LearningIsolationEvidenceGuardError(f"{name} must be positive integer")
    return value


def _sha(value: Any, regex: re.Pattern[str], name: str) -> str:
    if not isinstance(value, str) or not regex.fullmatch(value.lower()):
        raise LearningIsolationEvidenceGuardError(f"{name} malformed")
    return value.lower()


@dataclass(frozen=True)
class LearningIsolationEvidenceManifest:
    schema_version: str
    mission_id: str
    step_id: int
    run_id: int
    job_id: int
    artifact_id: int
    artifact_zip_sha256: str
    job_conclusion: str
    suite_results: Mapping[str, str]
    bound_blobs: Mapping[str, str]
    experience_delta: int
    appraisal_delta: int
    drive_delta: int
    exploration_delta: int
    preference_delta: int
    personality_delta: int
    trauma_relief_delta: int
    p_base_mutation_allowed: bool
    formal_effect: str
    formal_c_verification: str

    @classmethod
    def verify(cls, value: Any) -> "LearningIsolationEvidenceManifest":
        if not isinstance(value, Mapping):
            raise LearningIsolationEvidenceGuardError("manifest mapping required")
        try:
            m = cls(**dict(value))
        except TypeError as exc:
            raise LearningIsolationEvidenceGuardError("malformed manifest") from exc
        if m.schema_version != SCHEMA_VERSION or m.mission_id != MISSION_ID or m.step_id != STEP_ID:
            raise LearningIsolationEvidenceGuardError("scope/schema mismatch")
        _positive_int(m.run_id, "run_id"); _positive_int(m.job_id, "job_id"); _positive_int(m.artifact_id, "artifact_id")
        _sha(m.artifact_zip_sha256, SHA256_RE, "artifact_zip_sha256")
        if m.job_conclusion != "success":
            raise LearningIsolationEvidenceGuardError("job not successful")
        results = dict(m.suite_results)
        if set(results) != REQUIRED_SUITES or any(v != "success" for v in results.values()):
            raise LearningIsolationEvidenceGuardError("required isolation suites not exactly successful")
        blobs = dict(m.bound_blobs)
        if not blobs or any(_sha(v, BLOB_RE, f"bound_blobs.{k}") != v.lower() for k, v in blobs.items()):
            raise LearningIsolationEvidenceGuardError("bound blob set invalid")
        zero_fields = (m.experience_delta, m.appraisal_delta, m.drive_delta, m.exploration_delta,
                       m.preference_delta, m.personality_delta, m.trauma_relief_delta)
        if any(isinstance(v, bool) or v != 0 for v in zero_fields):
            raise LearningIsolationEvidenceGuardError("learning/cognitive delta must remain zero")
        if m.p_base_mutation_allowed is not False:
            raise LearningIsolationEvidenceGuardError("P_base mutation forbidden")
        if m.formal_effect != "NONE" or m.formal_c_verification != "NOT_CLAIMED":
            raise LearningIsolationEvidenceGuardError("formal boundary violated")
        return m


def review_projection(value: Any) -> dict[str, Any]:
    m = LearningIsolationEvidenceManifest.verify(value)
    return {
        "status": "NONFORMAL_LEARNING_ISOLATION_EVIDENCE_BOUND",
        "run_id": m.run_id,
        "job_id": m.job_id,
        "artifact_id": m.artifact_id,
        "suites": dict(m.suite_results),
        "experience_delta": 0,
        "personality_delta": 0,
        "p_base_mutation_allowed": False,
        "formal_effect": "NONE",
        "formal_c_verification": "NOT_CLAIMED",
        "whole_repository_taint_proof": False,
    }
