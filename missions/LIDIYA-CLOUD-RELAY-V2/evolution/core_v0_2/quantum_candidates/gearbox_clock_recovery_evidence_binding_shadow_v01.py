from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import re

SCHEMA_VERSION = "0.1-shadow"
MISSION_ID = "LCR-EVOLUTION-0005"
STEP_ID = 9
EXPECTED_RUN_ID = 32524738088
EXPECTED_JOB_ID = 96904287434
EXPECTED_ARTIFACT_ID = 9461767094
EXPECTED_ARTIFACT_ZIP_SHA256 = "c3bba5ce8ca2b90ca9ec78ed0f43aa9bc3aeaef903979e9e7d8808c715bd8429"
EXPECTED_V05_BLOBS = {
    "source": "9aaf3ad9f673944d548e2cd880c9286b98e72704",
    "test": "a4c98981561cf8c310c66c03367aa8fbf3954d61",
    "contract": "df4753a9eaa7d734afb81a7e32d7efb3fa6617b7",
    "workflow": "6ff4284e0856eaed56fbc810eb063240453ebc1e",
}
EXPECTED_COUNTS = {"V01": 9, "V03": 9, "V04": 5, "V05": 4}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BLOB_RE = re.compile(r"^[0-9a-f]{40}$")


class EvidenceBindingGuardError(ValueError):
    pass


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EvidenceBindingGuardError(f"{name} must be positive integer")
    return value


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value.lower()):
        raise EvidenceBindingGuardError(f"{name} must be lowercase 64-hex sha256")
    return value.lower()


def _blob(value: Any, name: str) -> str:
    if not isinstance(value, str) or not BLOB_RE.fullmatch(value.lower()):
        raise EvidenceBindingGuardError(f"{name} must be 40-hex git blob sha")
    return value.lower()


@dataclass(frozen=True)
class ClockRecoveryEvidenceManifest:
    schema_version: str
    mission_id: str
    step_id: int
    candidate_version: str
    run_id: int
    job_id: int
    artifact_id: int
    artifact_zip_sha256: str
    job_conclusion: str
    regression_counts: Mapping[str, int]
    v05_blobs: Mapping[str, str]
    formal_effect: str = "NONE"
    formal_c_verification: str = "NOT_CLAIMED"
    synthetic_provider_is_production_proof: bool = False

    @classmethod
    def verify(cls, value: Any) -> "ClockRecoveryEvidenceManifest":
        if not isinstance(value, Mapping):
            raise EvidenceBindingGuardError("evidence manifest mapping required")
        try:
            manifest = cls(**dict(value))
        except TypeError as exc:
            raise EvidenceBindingGuardError("malformed evidence manifest") from exc

        if manifest.schema_version != SCHEMA_VERSION:
            raise EvidenceBindingGuardError("evidence schema mismatch")
        if manifest.mission_id != MISSION_ID or manifest.step_id != STEP_ID:
            raise EvidenceBindingGuardError("mission/step evidence mismatch")
        if manifest.candidate_version != "V05":
            raise EvidenceBindingGuardError("candidate must be exact-current V05")
        if _positive_int(manifest.run_id, "run_id") != EXPECTED_RUN_ID:
            raise EvidenceBindingGuardError("workflow run id mismatch")
        if _positive_int(manifest.job_id, "job_id") != EXPECTED_JOB_ID:
            raise EvidenceBindingGuardError("workflow job id mismatch")
        if _positive_int(manifest.artifact_id, "artifact_id") != EXPECTED_ARTIFACT_ID:
            raise EvidenceBindingGuardError("artifact id mismatch")
        if _sha256(manifest.artifact_zip_sha256, "artifact_zip_sha256") != EXPECTED_ARTIFACT_ZIP_SHA256:
            raise EvidenceBindingGuardError("artifact digest mismatch")
        if manifest.job_conclusion != "success":
            raise EvidenceBindingGuardError("workflow job did not conclude success")

        counts = dict(manifest.regression_counts)
        if counts != EXPECTED_COUNTS:
            raise EvidenceBindingGuardError("regression count binding mismatch")

        blobs = {k: _blob(v, f"v05_blobs.{k}") for k, v in dict(manifest.v05_blobs).items()}
        if blobs != EXPECTED_V05_BLOBS:
            raise EvidenceBindingGuardError("exact-current V05 blob binding mismatch")

        if manifest.formal_effect != "NONE" or manifest.formal_c_verification != "NOT_CLAIMED":
            raise EvidenceBindingGuardError("non-formal evidence boundary violated")
        if manifest.synthetic_provider_is_production_proof is not False:
            raise EvidenceBindingGuardError("synthetic provider cannot become production proof")
        return manifest


def spirit_review_projection(value: Any) -> dict[str, Any]:
    manifest = ClockRecoveryEvidenceManifest.verify(value)
    return {
        "evidence_binding_status": "EXACT_CURRENT_NONFORMAL_EXECUTABLE_EVIDENCE_BOUND",
        "candidate_version": manifest.candidate_version,
        "run_id": manifest.run_id,
        "job_id": manifest.job_id,
        "artifact_id": manifest.artifact_id,
        "artifact_zip_sha256": manifest.artifact_zip_sha256,
        "regression_counts": dict(manifest.regression_counts),
        "v05_blobs": dict(manifest.v05_blobs),
        "formal_effect": "NONE",
        "formal_c_verification": "NOT_CLAIMED",
        "production_provider_key_liveness_proven": False,
        "experience_delta": 0,
        "personality_delta": 0,
        "p_base_mutation_allowed": False,
    }
