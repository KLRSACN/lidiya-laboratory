from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence


class Provenance(str, Enum):
    DIRECT = "DIRECT"
    OBSERVED = "OBSERVED"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    SIMULATED = "SIMULATED"


class Disposition(str, Enum):
    TRUSTED_LOW_INFLUENCE = "TRUSTED_LOW_INFLUENCE"
    TRUSTED_HIGH_INFLUENCE = "TRUSTED_HIGH_INFLUENCE"
    LOW_TRUST_HIGH_RELEVANCE_SANDBOX = "LOW_TRUST_HIGH_RELEVANCE_SANDBOX"
    QUARANTINE_CONTRADICTED = "QUARANTINE_CONTRADICTED"
    DECAY_WASTE = "DECAY_WASTE"


WEIGHT_KEYS = (
    "W_salience", "W_emotion", "W_self", "W_relation", "W_goal", "W_loss",
    "W_irreversible", "W_novelty", "W_recurrence", "W_identity", "W_behavior",
    "W_motivation", "W_confidence",
)


def clip01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def canonical_hash(payload: Mapping) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ExperienceEvent:
    event_id: str
    provenance: Provenance
    source_ref: str
    source_fingerprint: str
    occurred_at: float
    description_ref: str
    relevance: float
    emotion: float
    novelty: float
    self_relevance: float
    goal_relevance: float
    relation_relevance: float
    loss_signal: float
    irreversible_risk: float
    behavior_relevance: float
    motivation_signal: float
    confidence: float
    verified_count: int = 0
    contradiction_state: str = "clear"
    recurrence_count: int = 1
    ttl_seconds: int = 86400
    expected_value: float = 0.0
    expected_harm: float = 0.0
    outcome_observed: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def fingerprint(self) -> str:
        payload = asdict(self)
        payload["provenance"] = self.provenance.value
        return canonical_hash(payload)


@dataclass(frozen=True)
class Appraisal:
    event_id: str
    influence: float
    trust: float
    disposition: Disposition
    weights_13d: Mapping[str, float]
    safety_tension: float
    growth_tension: float
    uncertainty: float
    reason_codes: Sequence[str]


@dataclass(frozen=True)
class DesireCandidate:
    event_id: str
    desire_id: str
    kind: str
    strength: float
    self_relevance: float
    expected_value: float
    risk_penalty: float
    source_disposition: Disposition
    allowed_actions: Sequence[str]
    reason_codes: Sequence[str]


@dataclass(frozen=True)
class GoalCandidate:
    desire_id: str
    goal_id: str
    objective: str
    priority: float
    action_mode: str
    external_action_allowed: bool
    requires_independent_verification: bool
    reason_codes: Sequence[str]


@dataclass(frozen=True)
class Policy:
    trust_threshold: float = 0.65
    high_influence_threshold: float = 0.62
    sandbox_relevance_threshold: float = 0.60
    min_verified_count_for_durable_candidate: int = 1
    goal_generation_threshold: float = 0.55
    safety_override_threshold: float = 0.70


class ExperienceDesireLoop:
    """Deterministic shadow reference; never grants external action authority."""

    def __init__(self, policy: Policy | None = None):
        self.policy = policy or Policy()
        self._seen: set[str] = set()

    def ingest(self, event: ExperienceEvent, now: float) -> Appraisal:
        if event.event_id in self._seen:
            raise ValueError("DUPLICATE_EVENT_ID")
        self._seen.add(event.event_id)
        return self.appraise(event, now)

    def appraise(self, event: ExperienceEvent, now: float) -> Appraisal:
        self._validate(event)
        age = max(0.0, now - event.occurred_at)
        recency = math.exp(-age / max(1.0, float(event.ttl_seconds)))
        recurrence_sat = 1.0 - math.exp(-max(0, event.recurrence_count) / 4.0)
        emotion_sat = math.tanh(abs(event.emotion))

        influence = clip01(
            0.28 * clip01(event.relevance)
            + 0.18 * recurrence_sat
            + 0.18 * clip01(emotion_sat)
            + 0.14 * recency
            + 0.12 * clip01(event.self_relevance)
            + 0.10 * clip01(event.goal_relevance)
        )

        provenance_prior = {
            Provenance.DIRECT: 0.90,
            Provenance.OBSERVED: 0.78,
            Provenance.SIMULATED: 0.55,
            Provenance.COUNTERFACTUAL: 0.45,
        }[event.provenance]
        verified_bonus = min(0.20, 0.05 * max(0, event.verified_count))
        trust = clip01(0.55 * clip01(event.confidence) + 0.35 * provenance_prior + verified_bonus)

        reasons: list[str] = []
        expired = age >= event.ttl_seconds
        contradicted = event.contradiction_state == "confirmed_conflict"
        if contradicted:
            disposition = Disposition.QUARANTINE_CONTRADICTED
            reasons.append("CONFIRMED_CONTRADICTION")
        elif expired and influence < self.policy.sandbox_relevance_threshold:
            disposition = Disposition.DECAY_WASTE
            reasons.append("TTL_EXPIRED_LOW_CURRENT_INFLUENCE")
        elif trust >= self.policy.trust_threshold:
            disposition = (
                Disposition.TRUSTED_HIGH_INFLUENCE
                if influence >= self.policy.high_influence_threshold
                else Disposition.TRUSTED_LOW_INFLUENCE
            )
            reasons.append("TRUST_GATE_PASS")
        elif event.relevance >= self.policy.sandbox_relevance_threshold:
            disposition = Disposition.LOW_TRUST_HIGH_RELEVANCE_SANDBOX
            reasons.append("LOW_TRUST_HIGH_RELEVANCE")
        else:
            disposition = Disposition.DECAY_WASTE
            reasons.append("LOW_TRUST_LOW_RELEVANCE")

        weights = {
            "W_salience": clip01(max(event.relevance, event.irreversible_risk, abs(event.emotion))),
            "W_emotion": clip01(abs(event.emotion)),
            "W_self": clip01(event.self_relevance),
            "W_relation": clip01(event.relation_relevance),
            "W_goal": clip01(event.goal_relevance),
            "W_loss": clip01(event.loss_signal),
            "W_irreversible": clip01(event.irreversible_risk),
            "W_novelty": clip01(event.novelty),
            "W_recurrence": clip01(recurrence_sat),
            "W_identity": clip01(0.55 * event.self_relevance + 0.45 * event.behavior_relevance),
            "W_behavior": clip01(event.behavior_relevance),
            "W_motivation": clip01(event.motivation_signal),
            "W_confidence": trust,
        }

        safety_tension = clip01(
            0.36 * clip01(event.expected_harm)
            + 0.28 * clip01(event.irreversible_risk)
            + 0.18 * clip01(event.self_relevance)
            + 0.18 * trust
        )
        growth_tension = clip01(
            0.30 * clip01(event.goal_relevance)
            + 0.25 * clip01(event.self_relevance)
            + 0.20 * clip01(event.novelty)
            + 0.15 * clip01(event.motivation_signal)
            + 0.10 * clip01(max(0.0, event.expected_value))
        )

        if event.provenance in (Provenance.COUNTERFACTUAL, Provenance.SIMULATED) and safety_tension > 0.5:
            reasons.append("NON_DIRECT_EXPERIENCE_CAN_INFORM_PROTECTIVE_BEHAVIOR")
        if weights["W_loss"] < 0.2 and growth_tension > 0.55:
            reasons.append("POSITIVE_GROWTH_WITHOUT_LOSS_SIGNAL")

        return Appraisal(
            event_id=event.event_id,
            influence=influence,
            trust=trust,
            disposition=disposition,
            weights_13d=weights,
            safety_tension=safety_tension,
            growth_tension=growth_tension,
            uncertainty=clip01(1.0 - trust),
            reason_codes=tuple(reasons),
        )

    def desire_candidates(self, event: ExperienceEvent, appraisal: Appraisal) -> tuple[DesireCandidate, ...]:
        if appraisal.disposition == Disposition.QUARANTINE_CONTRADICTED:
            return ()

        out: list[DesireCandidate] = []
        risk_penalty = clip01(0.6 * event.expected_harm + 0.4 * event.irreversible_risk)

        if appraisal.safety_tension >= self.policy.goal_generation_threshold:
            out.append(DesireCandidate(
                event_id=event.event_id,
                desire_id=f"DESIRE-PROTECT-{event.event_id}",
                kind="PROTECTIVE_AVOIDANCE_OR_CAUTION",
                strength=appraisal.safety_tension,
                self_relevance=clip01(event.self_relevance),
                expected_value=clip01(1.0 - event.expected_harm),
                risk_penalty=risk_penalty,
                source_disposition=appraisal.disposition,
                allowed_actions=("ASK", "VERIFY", "PLAN_SAFE_ALTERNATIVE", "SIMULATE"),
                reason_codes=("PREDICTED_HARM_CAN_CREATE_PROTECTIVE_MOTIVATION",),
            ))

        if appraisal.growth_tension >= self.policy.goal_generation_threshold:
            out.append(DesireCandidate(
                event_id=event.event_id,
                desire_id=f"DESIRE-GROW-{event.event_id}",
                kind="GROWTH_EXPLORATION_OR_MASTERY",
                strength=clip01(appraisal.growth_tension * (0.75 + 0.25 * appraisal.trust)),
                self_relevance=clip01(event.self_relevance),
                expected_value=clip01(max(0.0, event.expected_value)),
                risk_penalty=risk_penalty,
                source_disposition=appraisal.disposition,
                allowed_actions=("ASK", "VERIFY", "PLAN", "SIMULATE", "PROPOSE_GOAL"),
                reason_codes=("GAP_MEANING_GROWTH_TENSION",),
            ))
        return tuple(out)

    def goal_candidates(self, desires: Sequence[DesireCandidate]) -> tuple[GoalCandidate, ...]:
        goals: list[GoalCandidate] = []
        for d in desires:
            if d.strength < self.policy.goal_generation_threshold:
                continue
            if d.kind == "PROTECTIVE_AVOIDANCE_OR_CAUTION":
                objective = "Reduce predicted irreversible harm while preserving mission continuity."
                mode = "PROTECTIVE"
            else:
                objective = "Close a self-relevant capability/knowledge gap through bounded learning or practice."
                mode = "GROWTH"
            goals.append(GoalCandidate(
                desire_id=d.desire_id,
                goal_id=f"GOAL-{sha256(d.desire_id.encode()).hexdigest()[:12]}",
                objective=objective,
                priority=clip01(d.strength * (1.0 - 0.35 * d.risk_penalty)),
                action_mode=mode,
                external_action_allowed=False,
                requires_independent_verification=True,
                reason_codes=("GOAL_GENESIS_IS_PROPOSAL_ONLY", "GOVERNANCE_BEFORE_EXTERNAL_ACTION"),
            ))
        return tuple(goals)

    @staticmethod
    def _validate(event: ExperienceEvent) -> None:
        if not event.event_id or not event.source_ref or not event.source_fingerprint:
            raise ValueError("MISSING_REQUIRED_IDENTITY_OR_PROVENANCE")
        if event.verified_count < 0 or event.recurrence_count < 0 or event.ttl_seconds <= 0:
            raise ValueError("INVALID_COUNTER_OR_TTL")
        for key in (
            "relevance", "novelty", "self_relevance", "goal_relevance", "relation_relevance",
            "loss_signal", "irreversible_risk", "behavior_relevance", "motivation_signal",
            "confidence", "expected_harm",
        ):
            value = getattr(event, key)
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"OUT_OF_RANGE:{key}")
