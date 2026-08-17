from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence


def canonical_hash(payload: object) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class VerifierRecord:
    verifier_id: str
    generation: int
    method_family: str
    policy_hash: str
    active: bool = True

    def key(self) -> str:
        return f"{self.verifier_id}:{self.generation}"


class VerifierRegistry:
    def __init__(self, records: Sequence[VerifierRecord]):
        self._records = {}
        for record in records:
            if not record.verifier_id or not record.method_family or not record.policy_hash:
                raise ValueError("INVALID_VERIFIER_RECORD")
            if record.key() in self._records:
                raise ValueError("DUPLICATE_VERIFIER_IDENTITY")
            self._records[record.key()] = record

    def registry_hash(self) -> str:
        return canonical_hash({"verifiers": [r.__dict__ for r in sorted(self._records.values(), key=lambda x: x.key())]})

    def accept_attestation(self, *, source_actor_id: str, attestation: Mapping[str, object]) -> bool:
        key = f"{attestation.get('verifier_id', '')}:{attestation.get('verifier_generation', '')}"
        record = self._records.get(key)
        if record is None or not record.active:
            return False
        if attestation.get("verdict") != "PASS":
            return False
        if attestation.get("verifier_id") == source_actor_id:
            return False
        if attestation.get("independent_of_source") is not True:
            return False
        if attestation.get("method_family") != record.method_family:
            return False
        if attestation.get("verification_policy_hash") != record.policy_hash:
            return False
        return True


@dataclass(frozen=True)
class DerivedAppraisalEnvelope:
    """Immutable, shadow-only appraisal binding.

    Numeric calibration thresholds remain TEST_REQUIRED. Domain bounds below are
    representation invariants, not learned trust thresholds.
    """

    source_event_hash: str
    evidence_set_hash: str
    verifier_envelope_hash: str
    anchor_registry_hash: str
    appraisal_policy_hash: str
    trust_score: float
    anchor_alignment: float
    cross_context_count: int
    feature_hash: str
    appraisal_binding_hash: str
    schema_version: str = "EDL-DERIVED-APPRAISAL-V0.1-TEST_REQUIRED"
    authority_from_drive: int = 0
    base_personality_write: bool = False
    external_action_allowed: bool = False

    def binding_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_event_hash": self.source_event_hash,
            "evidence_set_hash": self.evidence_set_hash,
            "verifier_envelope_hash": self.verifier_envelope_hash,
            "anchor_registry_hash": self.anchor_registry_hash,
            "appraisal_policy_hash": self.appraisal_policy_hash,
            "trust_score": self.trust_score,
            "anchor_alignment": self.anchor_alignment,
            "cross_context_count": self.cross_context_count,
            "feature_hash": self.feature_hash,
            "authority_from_drive": self.authority_from_drive,
            "base_personality_write": self.base_personality_write,
            "external_action_allowed": self.external_action_allowed,
        }

    def recompute_binding_hash(self) -> str:
        return canonical_hash(self.binding_payload())

    def verify(self) -> bool:
        if not all(
            (
                self.source_event_hash,
                self.evidence_set_hash,
                self.verifier_envelope_hash,
                self.anchor_registry_hash,
                self.appraisal_policy_hash,
                self.feature_hash,
                self.appraisal_binding_hash,
            )
        ):
            return False
        if not (0.0 <= self.trust_score <= 1.0):
            return False
        if not (-1.0 <= self.anchor_alignment <= 1.0):
            return False
        if self.cross_context_count < 0:
            return False
        if self.authority_from_drive != 0 or self.base_personality_write or self.external_action_allowed:
            return False
        return self.appraisal_binding_hash == self.recompute_binding_hash()

    @classmethod
    def build(
        cls,
        *,
        source_event_hash: str,
        evidence_set_hash: str,
        verifier_envelope_hash: str,
        anchor_registry_hash: str,
        appraisal_policy_hash: str,
        trust_score: float,
        anchor_alignment: float,
        cross_context_count: int,
        feature_hash: str,
    ) -> "DerivedAppraisalEnvelope":
        provisional = cls(
            source_event_hash=source_event_hash,
            evidence_set_hash=evidence_set_hash,
            verifier_envelope_hash=verifier_envelope_hash,
            anchor_registry_hash=anchor_registry_hash,
            appraisal_policy_hash=appraisal_policy_hash,
            trust_score=float(trust_score),
            anchor_alignment=float(anchor_alignment),
            cross_context_count=int(cross_context_count),
            feature_hash=feature_hash,
            appraisal_binding_hash="PENDING",
        )
        return cls(**{**provisional.__dict__, "appraisal_binding_hash": provisional.recompute_binding_hash()})


class LiveShadowAppraisalChokePoint:
    """Only canonical appraisal envelopes may enter the live-shadow integration lane.

    Legacy producer-authored ExperienceInput objects/dicts are deliberately not
    accepted here. This is a research candidate boundary, not formal adoption.
    """

    @staticmethod
    def admit(candidate: object) -> DerivedAppraisalEnvelope:
        if type(candidate) is not DerivedAppraisalEnvelope:
            raise ValueError("LEGACY_OR_UNBOUND_APPRAISAL_REJECTED")
        if not candidate.verify():
            raise ValueError("APPRAISAL_BINDING_INVALID")
        return candidate


class DeterministicFeatureExtractor:
    """Shadow-only feature extraction. Thresholds/coefficients remain TEST_REQUIRED."""

    FORBIDDEN_FIELDS = {"trust", "trust_score", "verified", "verification", "alignment", "authority", "personality_write"}
    SCHEMA_VERSION = "EDL-FEATURES-V0.1-TEST_REQUIRED"

    @classmethod
    def extract(cls, observation: Mapping[str, object]) -> dict[str, float]:
        for field in cls.FORBIDDEN_FIELDS:
            if field in observation:
                raise ValueError(f"RAW_EVENT_SELF_ASSERTION_FORBIDDEN:{field}")
        text = str(observation.get("text", ""))
        magnitude = float(observation.get("magnitude", 0.0))
        novelty = float(observation.get("novelty", 0.0))
        risk = float(observation.get("risk", 0.0))
        valence = float(observation.get("valence", 0.0))
        clip11 = lambda v: max(-1.0, min(1.0, v))
        clip01 = lambda v: max(0.0, min(1.0, v))
        return {
            "magnitude": clip01(magnitude),
            "novelty": clip01(novelty),
            "risk": clip01(risk),
            "valence": clip11(valence),
            "text_presence": 1.0 if text.strip() else 0.0,
        }
