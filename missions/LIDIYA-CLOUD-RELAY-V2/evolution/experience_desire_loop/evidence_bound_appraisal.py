from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Mapping, Sequence


def clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def clip_signed(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    evidence_hash: str
    source_actor_id: str
    source_artifact_hash: str
    semantic_subject_hash: str
    context_hash: str
    method_family: str

    def fingerprint(self) -> str:
        return canonical_hash(self.__dict__)


def evidence_set_hash(evidence_refs: Sequence[EvidenceRef]) -> str:
    refs = sorted(
        (
            {
                "evidence_id": e.evidence_id,
                "fingerprint": e.fingerprint(),
            }
            for e in evidence_refs
        ),
        key=lambda x: x["evidence_id"],
    )
    return canonical_hash({"evidence_refs": refs})


@dataclass(frozen=True)
class RawExperience:
    """
    Producer-supplied raw observation only.
    Intentionally has no trust, anchor_alignment, independently_verified,
    cross_context_count, satiation or personality eligibility fields.
    """
    event_id: str
    source_actor_id: str
    occurred_at: str
    raw_observation_ref: str
    evidence_refs: Sequence[EvidenceRef]
    raw_features: Mapping[str, float] = field(default_factory=dict)

    def evidence_set_hash(self) -> str:
        return evidence_set_hash(self.evidence_refs)

    def source_event_hash(self) -> str:
        return canonical_hash(
            {
                "event_id": self.event_id,
                "source_actor_id": self.source_actor_id,
                "occurred_at": self.occurred_at,
                "raw_observation_ref": self.raw_observation_ref,
                "evidence_set_hash": self.evidence_set_hash(),
            }
        )


@dataclass(frozen=True)
class VerifierAttestation:
    verifier_id: str
    verifier_generation: int
    verdict: str
    evidence_set_hash: str
    source_event_hash: str
    verified_at_ref: str
    verification_policy_hash: str
    method_family: str
    independent_of_source: bool

    def identity_key(self) -> str:
        return f"{self.verifier_id}:{self.verifier_generation}"

    def fingerprint(self) -> str:
        return canonical_hash(self.__dict__)


@dataclass(frozen=True)
class VerifierEnvelope:
    envelope_id: str
    source_event_hash: str
    evidence_set_hash: str
    verification_policy_hash: str
    attestations: Sequence[VerifierAttestation]

    def fingerprint(self) -> str:
        return canonical_hash(
            {
                "envelope_id": self.envelope_id,
                "source_event_hash": self.source_event_hash,
                "evidence_set_hash": self.evidence_set_hash,
                "verification_policy_hash": self.verification_policy_hash,
                "attestations": [
                    a.fingerprint()
                    for a in sorted(
                        self.attestations,
                        key=lambda a: (
                            a.verifier_id,
                            a.verifier_generation,
                            a.fingerprint(),
                        ),
                    )
                ],
            }
        )


@dataclass(frozen=True)
class ValueAnchor:
    anchor_id: str
    feature_weights: Mapping[str, float]
    importance: float
    stability: float
    version: int = 1

    def fingerprint(self) -> str:
        return canonical_hash(
            {
                "anchor_id": self.anchor_id,
                "feature_weights": {
                    k: round(clip_signed(v), 8)
                    for k, v in sorted(self.feature_weights.items())
                },
                "importance": round(clip01(self.importance), 8),
                "stability": round(clip01(self.stability), 8),
                "version": int(self.version),
            }
        )


@dataclass(frozen=True)
class AppraisalPolicy:
    policy_id: str = "EDL-EVIDENCE-BOUND-APPRAISER-V0.1"
    min_independent_verifiers: int = 1
    min_method_families: int = 1
    min_evidence_refs: int = 1
    base_trust: float = 0.35
    verifier_bonus: float = 0.20
    method_bonus: float = 0.15
    evidence_bonus: float = 0.10
    max_verifier_bonus_count: int = 2
    max_method_bonus_count: int = 2
    max_evidence_bonus_count: int = 3

    def fingerprint(self) -> str:
        return canonical_hash(self.__dict__)


@dataclass(frozen=True)
class DerivedAppraisal:
    appraisal_id: str
    source_event_hash: str
    trust_eligibility: bool
    trust_score: float
    anchor_alignment: Mapping[str, float]
    lineage_root_hash: str
    context_hashes: Sequence[str]
    evidence_set_hash: str
    anchor_registry_hash: str
    appraisal_policy_hash: str
    verifier_envelope_hash: str
    independent_verifier_count: int
    independent_method_count: int
    evidence_ref_count: int
    reason_codes: Sequence[str]

    def fingerprint(self) -> str:
        return canonical_hash(
            {
                "appraisal_id": self.appraisal_id,
                "source_event_hash": self.source_event_hash,
                "trust_eligibility": self.trust_eligibility,
                "trust_score": round(self.trust_score, 8),
                "anchor_alignment": {
                    k: round(v, 8)
                    for k, v in sorted(self.anchor_alignment.items())
                },
                "lineage_root_hash": self.lineage_root_hash,
                "context_hashes": list(self.context_hashes),
                "evidence_set_hash": self.evidence_set_hash,
                "anchor_registry_hash": self.anchor_registry_hash,
                "appraisal_policy_hash": self.appraisal_policy_hash,
                "verifier_envelope_hash": self.verifier_envelope_hash,
                "independent_verifier_count": self.independent_verifier_count,
                "independent_method_count": self.independent_method_count,
                "evidence_ref_count": self.evidence_ref_count,
                "reason_codes": list(self.reason_codes),
            }
        )


class EvidenceBoundAppraiser:
    """
    Deterministic appraisal boundary.

    Raw event producers may submit observations/features and evidence references,
    but cannot author authoritative trust, verification, alignment, lineage or
    cross-context counts. Those are derived here from pinned evidence, verifier
    envelopes, anchor registry and appraisal policy.
    """

    def __init__(
        self,
        anchors: Sequence[ValueAnchor],
        verification_policy_hash: str,
        policy: AppraisalPolicy | None = None,
    ):
        self.policy = policy or AppraisalPolicy()
        self.verification_policy_hash = verification_policy_hash
        self.anchors = {a.anchor_id: a for a in anchors}
        if len(self.anchors) != len(tuple(anchors)):
            raise ValueError("DUPLICATE_ANCHOR_ID")
        self.anchor_registry_hash = canonical_hash(
            {
                "anchors": [
                    {
                        "anchor_id": a.anchor_id,
                        "fingerprint": a.fingerprint(),
                    }
                    for a in sorted(self.anchors.values(), key=lambda a: a.anchor_id)
                ]
            }
        )

    def appraise(
        self,
        raw: RawExperience,
        verifier_envelope: VerifierEnvelope,
    ) -> DerivedAppraisal:
        self._validate_raw(raw)
        source_event_hash = raw.source_event_hash()
        e_set_hash = raw.evidence_set_hash()
        reasons: list[str] = []

        envelope_binding_valid = (
            verifier_envelope.source_event_hash == source_event_hash
            and verifier_envelope.evidence_set_hash == e_set_hash
            and verifier_envelope.verification_policy_hash
            == self.verification_policy_hash
        )

        accepted_attestations: dict[str, VerifierAttestation] = {}
        if envelope_binding_valid:
            for att in verifier_envelope.attestations:
                if att.verdict != "PASS":
                    continue
                if not att.independent_of_source:
                    continue
                if att.verifier_id == raw.source_actor_id:
                    continue
                if att.source_event_hash != source_event_hash:
                    continue
                if att.evidence_set_hash != e_set_hash:
                    continue
                if att.verification_policy_hash != self.verification_policy_hash:
                    continue
                if not att.verified_at_ref or not att.method_family:
                    continue
                accepted_attestations.setdefault(att.identity_key(), att)
        else:
            reasons.append("VERIFIER_ENVELOPE_BINDING_INVALID")

        verifier_ids = {a.verifier_id for a in accepted_attestations.values()}
        method_families = {a.method_family for a in accepted_attestations.values()}
        evidence_count = len({e.evidence_id for e in raw.evidence_refs})
        trust_eligibility = (
            envelope_binding_valid
            and len(verifier_ids) >= self.policy.min_independent_verifiers
            and len(method_families) >= self.policy.min_method_families
            and evidence_count >= self.policy.min_evidence_refs
        )

        if trust_eligibility:
            reasons.append("EVIDENCE_BOUND_TRUST_GATE_PASS")
        else:
            reasons.append("EVIDENCE_BOUND_TRUST_GATE_FAIL")

        trust_score = 0.0
        if trust_eligibility:
            trust_score = clip01(
                self.policy.base_trust
                + self.policy.verifier_bonus
                * min(self.policy.max_verifier_bonus_count, len(verifier_ids))
                + self.policy.method_bonus
                * min(self.policy.max_method_bonus_count, len(method_families))
                + self.policy.evidence_bonus
                * min(self.policy.max_evidence_bonus_count, evidence_count)
            )

        anchor_alignment: dict[str, float] = {}
        for anchor_id, anchor in self.anchors.items():
            numerator = 0.0
            denom = 0.0
            for feature, weight in anchor.feature_weights.items():
                if feature not in raw.raw_features:
                    continue
                w = clip_signed(weight)
                numerator += clip_signed(raw.raw_features[feature]) * w
                denom += abs(w)
            base_alignment = 0.0 if denom == 0.0 else clip_signed(numerator / denom)
            anchor_alignment[anchor_id] = clip_signed(
                base_alignment * clip01(anchor.importance) * clip01(anchor.stability)
            )

        lineage_material = sorted(
            {
                (
                    e.semantic_subject_hash,
                    e.source_actor_id,
                    e.source_artifact_hash,
                )
                for e in raw.evidence_refs
            }
        )
        lineage_root_hash = canonical_hash(
            {
                "lineage_material": [
                    {
                        "semantic_subject_hash": subject,
                        "source_actor_id": actor,
                        "source_artifact_hash": artifact,
                    }
                    for subject, actor, artifact in lineage_material
                ]
            }
        )
        context_hashes = tuple(sorted({e.context_hash for e in raw.evidence_refs}))

        return DerivedAppraisal(
            appraisal_id=f"APPRAISAL-{source_event_hash[:16]}",
            source_event_hash=source_event_hash,
            trust_eligibility=trust_eligibility,
            trust_score=trust_score,
            anchor_alignment=anchor_alignment,
            lineage_root_hash=lineage_root_hash,
            context_hashes=context_hashes,
            evidence_set_hash=e_set_hash,
            anchor_registry_hash=self.anchor_registry_hash,
            appraisal_policy_hash=self.policy.fingerprint(),
            verifier_envelope_hash=verifier_envelope.fingerprint(),
            independent_verifier_count=len(verifier_ids),
            independent_method_count=len(method_families),
            evidence_ref_count=evidence_count,
            reason_codes=tuple(reasons),
        )

    @staticmethod
    def _validate_raw(raw: RawExperience) -> None:
        if (
            not raw.event_id
            or not raw.source_actor_id
            or not raw.occurred_at
            or not raw.raw_observation_ref
            or not raw.evidence_refs
        ):
            raise ValueError("MISSING_RAW_EXPERIENCE_FIELD")
        if len({e.evidence_id for e in raw.evidence_refs}) != len(raw.evidence_refs):
            raise ValueError("DUPLICATE_EVIDENCE_ID")
        for e in raw.evidence_refs:
            if (
                not e.evidence_hash
                or not e.source_actor_id
                or not e.source_artifact_hash
                or not e.semantic_subject_hash
                or not e.context_hash
                or not e.method_family
            ):
                raise ValueError("INCOMPLETE_EVIDENCE_REF")
        for feature, value in raw.raw_features.items():
            if not -1.0 <= float(value) <= 1.0:
                raise ValueError(f"OUT_OF_RANGE_RAW_FEATURE:{feature}")


@dataclass(frozen=True)
class CrossContextSummary:
    accepted_appraisal_ids: Sequence[str]
    independent_context_count: int
    independent_lineage_count: int
    evidence_set_hash: str


class CrossContextEvidenceLedger:
    """Cross-context/lineage counts are derived, never producer supplied."""

    @staticmethod
    def summarize(appraisals: Sequence[DerivedAppraisal]) -> CrossContextSummary:
        accepted: dict[str, DerivedAppraisal] = {}
        for appraisal in appraisals:
            if not appraisal.trust_eligibility:
                continue
            accepted.setdefault(appraisal.fingerprint(), appraisal)

        contexts: set[str] = set()
        lineages: set[str] = set()
        evidence_hashes: set[str] = set()
        ids: list[str] = []
        for appraisal in accepted.values():
            contexts.update(appraisal.context_hashes)
            lineages.add(appraisal.lineage_root_hash)
            evidence_hashes.add(appraisal.evidence_set_hash)
            ids.append(appraisal.appraisal_id)

        return CrossContextSummary(
            accepted_appraisal_ids=tuple(sorted(ids)),
            independent_context_count=len(contexts),
            independent_lineage_count=len(lineages),
            evidence_set_hash=canonical_hash(
                {"accepted_evidence_set_hashes": sorted(evidence_hashes)}
            ),
        )
