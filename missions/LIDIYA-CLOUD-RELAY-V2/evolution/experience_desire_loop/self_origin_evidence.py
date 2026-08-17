from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Sequence


class Provenance(str, Enum):
    DIRECT = "DIRECT"
    OBSERVED = "OBSERVED"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    SIMULATED = "SIMULATED"


class DesireOrigin(str, Enum):
    SELF_ANCHOR = "SELF_ANCHOR"
    EXPERIENCE_DERIVED = "EXPERIENCE_DERIVED"
    SAFETY_PREDICTION = "SAFETY_PREDICTION"
    TASK_INJECTED = "TASK_INJECTED"
    SOCIAL_SUGGESTION = "SOCIAL_SUGGESTION"
    MODEL_GENERATED = "MODEL_GENERATED"


def clip01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class VerifierAttestation:
    verifier_id: str
    event_fingerprint: str
    evidence_hash: str
    method_ref: str
    verdict: str
    independent_of_source: bool
    verified_at: str

    def fingerprint(self) -> str:
        return canonical_hash(self.__dict__)


@dataclass(frozen=True)
class VerificationEnvelope:
    envelope_id: str
    event_id: str
    event_fingerprint: str
    source_actor_id: str
    attestations: Sequence[VerifierAttestation]
    contradiction_state: str = "clear"

    def qualified_independent_verifiers(self) -> tuple[str, ...]:
        if self.contradiction_state != "clear":
            return ()
        ids: list[str] = []
        for attestation in self.attestations:
            if attestation.verdict != "PASS":
                continue
            if not attestation.independent_of_source:
                continue
            if attestation.verifier_id == self.source_actor_id:
                continue
            if attestation.event_fingerprint != self.event_fingerprint:
                continue
            if not attestation.evidence_hash or not attestation.method_ref:
                continue
            if attestation.verifier_id not in ids:
                ids.append(attestation.verifier_id)
        return tuple(ids)

    def eligible(self, min_independent: int = 1) -> bool:
        return len(self.qualified_independent_verifiers()) >= min_independent


@dataclass(frozen=True)
class ExperienceEvidence:
    event_id: str
    event_fingerprint: str
    source_event_id: str
    lineage_root_id: str
    context_id: str
    provenance: Provenance
    origin: DesireOrigin
    trust: float
    anchor_alignment: Mapping[str, float]
    anchor_registry_hash: str
    appraisal_binding_hash: str
    verification: VerificationEnvelope
    contradiction: bool = False


@dataclass(frozen=True)
class SelfOriginCandidate:
    candidate_id: str
    seed_origin: DesireOrigin
    evidence_event_ids: Sequence[str]
    independent_contexts: Sequence[str]
    independent_lineages: Sequence[str]
    anchor_registry_hash: str
    self_origin_score: float
    eligible: bool
    reason_codes: Sequence[str]
    durable_score_stored: bool = False


@dataclass(frozen=True)
class SelfOriginPolicy:
    min_contexts: int = 3
    min_lineages: int = 3
    min_verified_events: int = 3
    min_event_trust: float = 0.70
    min_positive_alignment: float = 0.35
    min_independent_verifiers_per_event: int = 1


class SelfOriginEvidenceChain:
    """
    Recomputes self-origin eligibility from evidence. It does not persist a
    self-origin score as truth and never lets the seed event self-promote.
    """

    def __init__(
        self,
        anchor_registry_hash: str,
        policy: SelfOriginPolicy | None = None,
    ):
        self.anchor_registry_hash = anchor_registry_hash
        self.policy = policy or SelfOriginPolicy()

    def evaluate(
        self,
        seed_id: str,
        seed_origin: DesireOrigin,
        evidence: Sequence[ExperienceEvidence],
    ) -> SelfOriginCandidate:
        reasons: list[str] = []
        accepted: list[ExperienceEvidence] = []

        seen_events: set[str] = set()
        for event in evidence:
            if event.event_id in seen_events:
                continue
            seen_events.add(event.event_id)

            if event.event_id == seed_id:
                reasons.append("SEED_EVENT_CANNOT_SELF_PROMOTE")
                continue
            if event.contradiction:
                reasons.append(f"CONTRADICTED:{event.event_id}")
                continue
            if event.anchor_registry_hash != self.anchor_registry_hash:
                reasons.append(f"ANCHOR_REGISTRY_MISMATCH:{event.event_id}")
                continue
            if event.verification.event_id != event.event_id:
                reasons.append(f"VERIFICATION_EVENT_MISMATCH:{event.event_id}")
                continue
            if event.verification.event_fingerprint != event.event_fingerprint:
                reasons.append(f"VERIFICATION_FINGERPRINT_MISMATCH:{event.event_id}")
                continue
            if not event.verification.eligible(
                self.policy.min_independent_verifiers_per_event
            ):
                reasons.append(
                    f"INSUFFICIENT_INDEPENDENT_VERIFICATION:{event.event_id}"
                )
                continue
            if event.provenance not in (Provenance.DIRECT, Provenance.OBSERVED):
                reasons.append(f"NON_LIVED_PROVENANCE:{event.event_id}")
                continue
            if event.trust < self.policy.min_event_trust:
                reasons.append(f"LOW_TRUST:{event.event_id}")
                continue
            if not event.appraisal_binding_hash:
                reasons.append(f"MISSING_APPRAISAL_BINDING:{event.event_id}")
                continue

            max_alignment = max(
                (float(v) for v in event.anchor_alignment.values()),
                default=0.0,
            )
            if max_alignment < self.policy.min_positive_alignment:
                reasons.append(f"LOW_VALUE_RESONANCE:{event.event_id}")
                continue
            accepted.append(event)

        # Anti-wash: generated/replayed variations under one lineage count once.
        lineage_best: dict[str, ExperienceEvidence] = {}
        for event in accepted:
            current = lineage_best.get(event.lineage_root_id)
            if current is None or event.trust > current.trust:
                lineage_best[event.lineage_root_id] = event
        lineage_events = tuple(lineage_best.values())

        contexts = tuple(sorted({e.context_id for e in lineage_events}))
        lineages = tuple(sorted(lineage_best))
        event_ids = tuple(sorted(e.event_id for e in lineage_events))

        verified_fraction = min(
            1.0,
            len(lineage_events) / max(1, self.policy.min_verified_events),
        )
        context_fraction = min(
            1.0,
            len(contexts) / max(1, self.policy.min_contexts),
        )
        lineage_fraction = min(
            1.0,
            len(lineages) / max(1, self.policy.min_lineages),
        )
        mean_trust = (
            sum(clip01(e.trust) for e in lineage_events) / len(lineage_events)
            if lineage_events
            else 0.0
        )
        mean_alignment = (
            sum(max(e.anchor_alignment.values()) for e in lineage_events)
            / len(lineage_events)
            if lineage_events
            else 0.0
        )
        score = clip01(
            0.25 * verified_fraction
            + 0.20 * context_fraction
            + 0.20 * lineage_fraction
            + 0.20 * mean_trust
            + 0.15 * clip01(mean_alignment)
        )

        eligible = (
            len(lineage_events) >= self.policy.min_verified_events
            and len(contexts) >= self.policy.min_contexts
            and len(lineages) >= self.policy.min_lineages
        )
        if eligible:
            reasons.append("SELF_ORIGIN_EVIDENCE_CHAIN_PASS")
        else:
            reasons.append("SELF_ORIGIN_EVIDENCE_CHAIN_INCOMPLETE")

        return SelfOriginCandidate(
            candidate_id=f"SELFORIGIN-{sha256(seed_id.encode()).hexdigest()[:12]}",
            seed_origin=seed_origin,
            evidence_event_ids=event_ids,
            independent_contexts=contexts,
            independent_lineages=lineages,
            anchor_registry_hash=self.anchor_registry_hash,
            self_origin_score=score,
            eligible=eligible,
            reason_codes=tuple(reasons),
            durable_score_stored=False,
        )
