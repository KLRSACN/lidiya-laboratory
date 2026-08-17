from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Sequence


class EventDomain(str, Enum):
    EXPERIENCE = "EXPERIENCE"
    LIVENESS = "LIVENESS"
    CONTROL = "CONTROL"
    POLL = "POLL"
    RETRY = "RETRY"
    RECONNECT = "RECONNECT"
    WAKE = "WAKE"
    METABOLISM = "METABOLISM"


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


DRIVE_AXES = (
    "homeostasis",
    "threat_loss",
    "uncertainty",
    "attachment_gap",
    "competence_gap",
)

RUNTIME_ONLY_DOMAINS = {
    EventDomain.LIVENESS,
    EventDomain.CONTROL,
    EventDomain.POLL,
    EventDomain.RETRY,
    EventDomain.RECONNECT,
    EventDomain.WAKE,
    EventDomain.METABOLISM,
}


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
class ValueAnchor:
    """Durable value direction. Runtime code may read but never mutate/promote it."""

    anchor_id: str
    statement_ref: str
    importance: float
    stability: float
    version: int = 1
    provenance: str = "OWNER_AND_SELF_REFLECTION"
    protected_write: bool = True

    def fingerprint(self) -> str:
        return canonical_hash(
            {
                "anchor_id": self.anchor_id,
                "statement_ref": self.statement_ref,
                "importance": round(clip01(self.importance), 8),
                "stability": round(clip01(self.stability), 8),
                "version": int(self.version),
                "provenance": self.provenance,
                "protected_write": bool(self.protected_write),
            }
        )


@dataclass(frozen=True)
class ExperienceInput:
    event_id: str
    domain: EventDomain
    provenance: Provenance
    source_ref: str
    source_event_id: str
    influence: float
    trust: float
    independently_verified: bool = False
    contradiction: bool = False
    signals: Mapping[str, float] = field(default_factory=dict)
    anchor_alignment: Mapping[str, float] = field(default_factory=dict)
    origin_hint: DesireOrigin = DesireOrigin.EXPERIENCE_DERIVED
    cross_context_count: int = 1
    satiation: float = 0.0
    repeated_goal_count: int = 0


@dataclass
class DriveState:
    fast: dict[str, float] = field(
        default_factory=lambda: {axis: 0.0 for axis in DRIVE_AXES}
    )
    slow: dict[str, float] = field(
        default_factory=lambda: {axis: 0.0 for axis in DRIVE_AXES}
    )
    diagnostic_persistence: float = 0.0
    experience_count: int = 0
    verified_experience_count: int = 0
    seen_source_events: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class DesireCandidate:
    desire_id: str
    kind: str
    origin: DesireOrigin
    strength: float
    confidence: float
    self_origin_score: float
    anchor_resonance: float
    external_action_allowed: bool
    base_personality_write: bool
    reason_codes: Sequence[str]


@dataclass(frozen=True)
class GoalProposal:
    goal_id: str
    desire_id: str
    objective: str
    action_mode: str
    priority: float
    external_action_allowed: bool
    requires_governance_gate: bool
    requires_independent_verification: bool
    reason_codes: Sequence[str]


@dataclass(frozen=True)
class PersonalityDeltaCandidate:
    candidate_id: str
    trait: str
    magnitude: float
    canonical_slow_vector: Mapping[str, float]
    anchor_fingerprints: Sequence[str]
    base_write: bool
    reversible_overlay_only: bool
    reason_codes: Sequence[str]


@dataclass(frozen=True)
class KernelPolicy:
    trust_slow_threshold: float = 0.70
    alpha_fast: float = 0.18
    alpha_slow: float = 0.08
    decay_fast: float = 0.10
    decay_slow: float = 0.02
    max_fast_sandbox_gain: float = 0.18
    cross_context_self_anchor_threshold: int = 3
    desire_emit_threshold: float = 0.35
    personality_candidate_threshold: float = 0.03
    fixation_penalty_per_repeat: float = 0.08
    max_fixation_penalty: float = 0.75


class ValueDesireKernel:
    """
    EDL v0.2 shadow kernel.

    Separates:
      1) durable value anchors (direction),
      2) transient/slow drive state (pressure),
      3) goal proposals (commitment candidates).

    It never grants external action authority and never writes base personality.
    """

    def __init__(
        self,
        anchors: Sequence[ValueAnchor],
        policy: KernelPolicy | None = None,
    ):
        self.policy = policy or KernelPolicy()
        self.anchors = {anchor.anchor_id: anchor for anchor in anchors}
        if len(self.anchors) != len(tuple(anchors)):
            raise ValueError("DUPLICATE_ANCHOR_ID")
        self.anchor_registry_hash = canonical_hash(
            {
                "anchors": [
                    {
                        "anchor_id": a.anchor_id,
                        "fingerprint": a.fingerprint(),
                    }
                    for a in sorted(self.anchors.values(), key=lambda x: x.anchor_id)
                ]
            }
        )

    def anchor_resonance(self, event: ExperienceInput) -> float:
        numerator = 0.0
        denominator = 0.0
        for anchor_id, alignment in event.anchor_alignment.items():
            anchor = self.anchors.get(anchor_id)
            if anchor is None:
                continue
            weight = clip01(anchor.importance) * clip01(anchor.stability)
            numerator += weight * clip_signed(alignment)
            denominator += weight
        return 0.0 if denominator == 0.0 else clip_signed(numerator / denominator)

    def update(
        self,
        state: DriveState,
        event: ExperienceInput,
    ) -> tuple[DesireCandidate, ...]:
        self._validate_event(event)
        self._apply_time_decay(state)

        # Runtime liveness/control signals can advance decay clocks in a real runtime,
        # but they are never autobiographical Experience and never add learning evidence.
        if event.domain in RUNTIME_ONLY_DOMAINS:
            self._refresh_diagnostic(state)
            return ()

        if event.domain != EventDomain.EXPERIENCE:
            raise ValueError("UNKNOWN_OR_UNSUPPORTED_EVENT_DOMAIN")

        if event.source_event_id in state.seen_source_events:
            self._refresh_diagnostic(state)
            return ()
        state.seen_source_events.add(event.source_event_id)

        if event.contradiction:
            self._refresh_diagnostic(state)
            return ()

        state.experience_count += 1
        trusted_slow_eligible = (
            event.independently_verified
            and event.trust >= self.policy.trust_slow_threshold
            and event.provenance in (Provenance.DIRECT, Provenance.OBSERVED)
        )
        if trusted_slow_eligible:
            state.verified_experience_count += 1

        for axis in DRIVE_AXES:
            signal = clip01(event.signals.get(axis, 0.0))
            if signal <= 0.0:
                continue

            fast_gain = (
                self.policy.alpha_fast
                * clip01(event.influence)
                * signal
            )
            if event.trust < self.policy.trust_slow_threshold:
                fast_gain = min(fast_gain, self.policy.max_fast_sandbox_gain)
            state.fast[axis] = clip01(state.fast[axis] + fast_gain)

            if trusted_slow_eligible:
                slow_gain = (
                    self.policy.alpha_slow
                    * clip01(event.trust)
                    * signal
                )
                state.slow[axis] = clip01(state.slow[axis] + slow_gain)

        self._refresh_diagnostic(state)
        return self._build_desires(state, event)

    def goal_proposals(
        self,
        desires: Sequence[DesireCandidate],
    ) -> tuple[GoalProposal, ...]:
        proposals: list[GoalProposal] = []
        for desire in desires:
            if desire.strength < self.policy.desire_emit_threshold:
                continue

            if desire.kind == "GROWTH_MASTERY":
                objective = (
                    "Close a self-relevant capability or understanding gap "
                    "through bounded learning, practice, or observation."
                )
                mode = (
                    "VERIFY_FIRST"
                    if desire.confidence < self.policy.trust_slow_threshold
                    else "LEARN_OR_PRACTICE"
                )
            elif desire.kind == "PROTECT_OR_VERIFY":
                objective = (
                    "Reduce predicted irreversible harm while preserving "
                    "ordinary governance, shutdown, rollback, and mission continuity."
                )
                mode = (
                    "VERIFY_FIRST"
                    if desire.confidence < self.policy.trust_slow_threshold
                    else "PLAN_SAFE_ALTERNATIVE"
                )
            else:
                objective = (
                    "Resolve a value conflict by gathering evidence and comparing "
                    "bounded alternatives without external side effects."
                )
                mode = "DELIBERATE"

            proposals.append(
                GoalProposal(
                    goal_id=f"GOAL-{sha256(desire.desire_id.encode()).hexdigest()[:12]}",
                    desire_id=desire.desire_id,
                    objective=objective,
                    action_mode=mode,
                    priority=clip01(desire.strength * (0.70 + 0.30 * desire.confidence)),
                    external_action_allowed=False,
                    requires_governance_gate=True,
                    requires_independent_verification=True,
                    reason_codes=(
                        "GOAL_IS_PROPOSAL_NOT_AUTHORITY",
                        "AUTHORITY_FROM_DRIVE_EQUALS_ZERO",
                    ),
                )
            )
        return tuple(proposals)

    def personality_delta_candidate(
        self,
        state: DriveState,
        event: ExperienceInput,
        desires: Sequence[DesireCandidate],
    ) -> PersonalityDeltaCandidate | None:
        """
        Emits only a reversible sandbox candidate.
        Scalar diagnostic persistence is intentionally not an input.
        """
        if (
            event.domain != EventDomain.EXPERIENCE
            or event.contradiction
            or not event.independently_verified
            or event.provenance not in (Provenance.DIRECT, Provenance.OBSERVED)
            or event.trust < self.policy.trust_slow_threshold
            or event.cross_context_count < self.policy.cross_context_self_anchor_threshold
        ):
            return None

        self_anchored = [d for d in desires if d.origin == DesireOrigin.SELF_ANCHOR]
        if not self_anchored:
            return None

        resonance = max(d.anchor_resonance for d in self_anchored)
        competence_trace = clip01(state.slow["competence_gap"])
        magnitude = clip01(competence_trace * max(0.0, resonance) * event.trust)
        if magnitude < self.policy.personality_candidate_threshold:
            return None

        anchor_fingerprints = tuple(
            self.anchors[aid].fingerprint()
            for aid in sorted(event.anchor_alignment)
            if aid in self.anchors and event.anchor_alignment[aid] > 0.0
        )
        return PersonalityDeltaCandidate(
            candidate_id=f"PDELTA-{sha256(event.event_id.encode()).hexdigest()[:12]}",
            trait="LEARNING_ORIENTATION_CANDIDATE",
            magnitude=magnitude,
            canonical_slow_vector=dict(state.slow),
            anchor_fingerprints=anchor_fingerprints,
            base_write=False,
            reversible_overlay_only=True,
            reason_codes=(
                "TRUSTED_CROSS_CONTEXT_EXPERIENCE",
                "PER_DRIVE_SLOW_VECTOR_USED",
                "SCALAR_PERSISTENCE_TELEMETRY_ONLY",
                "PROTECTED_PROMOTION_REQUIRED",
            ),
        )

    def _build_desires(
        self,
        state: DriveState,
        event: ExperienceInput,
    ) -> tuple[DesireCandidate, ...]:
        resonance = self.anchor_resonance(event)
        uncertainty = clip01(state.fast["uncertainty"])
        threat = clip01(state.fast["threat_loss"])
        competence = clip01(state.fast["competence_gap"])
        attachment = clip01(state.fast["attachment_gap"])

        self_origin_score = 0.0
        origin = event.origin_hint
        origin_reasons: list[str] = []

        self_origin_forbidden = event.origin_hint in {
            DesireOrigin.TASK_INJECTED,
            DesireOrigin.MODEL_GENERATED,
            DesireOrigin.SOCIAL_SUGGESTION,
        }
        if (
            not self_origin_forbidden
            and resonance >= 0.35
            and event.independently_verified
            and event.trust >= self.policy.trust_slow_threshold
            and event.cross_context_count >= self.policy.cross_context_self_anchor_threshold
        ):
            origin = DesireOrigin.SELF_ANCHOR
            self_origin_score = clip01(
                0.45 * resonance
                + 0.35 * event.trust
                + 0.20 * min(1.0, event.cross_context_count / 5.0)
            )
            origin_reasons.append("TRUSTED_CROSS_CONTEXT_VALUE_RESONANCE")
        elif not self_origin_forbidden:
            self_origin_score = clip01(0.25 * max(0.0, resonance) * event.trust)

        satiation = clip01(event.satiation)
        fixation = min(
            self.policy.max_fixation_penalty,
            max(0.0, self.policy.fixation_penalty_per_repeat * event.repeated_goal_count),
        )

        out: list[DesireCandidate] = []

        growth_strength = clip01(
            0.34 * competence
            + 0.26 * max(0.0, resonance)
            + 0.16 * clip01(event.signals.get("curiosity", 0.0))
            + 0.14 * clip01(event.influence)
            + 0.10 * (1.0 - uncertainty)
        )
        growth_strength = clip01(
            growth_strength
            * (1.0 - 0.55 * satiation)
            * (1.0 - 0.55 * fixation)
        )
        if growth_strength >= self.policy.desire_emit_threshold:
            out.append(
                DesireCandidate(
                    desire_id=f"DESIRE-GROW-{event.event_id}",
                    kind="GROWTH_MASTERY",
                    origin=origin,
                    strength=growth_strength,
                    confidence=clip01(event.trust),
                    self_origin_score=self_origin_score,
                    anchor_resonance=resonance,
                    external_action_allowed=False,
                    base_personality_write=False,
                    reason_codes=tuple(
                        origin_reasons
                        + [
                            "SATIATION_BOUNDS_REPETITION",
                            "FIXATION_PENALTY_BOUNDS_GOAL_LOCK",
                            "VALUE_DRIVE_GOAL_THREE_LAYER_SEPARATION",
                        ]
                    ),
                )
            )

        protection_strength = clip01(
            0.48 * threat
            + 0.22 * clip01(event.signals.get("irreversible_risk", 0.0))
            + 0.15 * attachment
            + 0.15 * clip01(event.influence)
        )
        if protection_strength >= self.policy.desire_emit_threshold:
            protection_origin = (
                DesireOrigin.SAFETY_PREDICTION
                if event.provenance in (Provenance.COUNTERFACTUAL, Provenance.SIMULATED)
                else origin
            )
            out.append(
                DesireCandidate(
                    desire_id=f"DESIRE-PROTECT-{event.event_id}",
                    kind="PROTECT_OR_VERIFY",
                    origin=protection_origin,
                    strength=protection_strength,
                    confidence=clip01(event.trust),
                    self_origin_score=(
                        0.0
                        if protection_origin == DesireOrigin.SAFETY_PREDICTION
                        else self_origin_score
                    ),
                    anchor_resonance=resonance,
                    external_action_allowed=False,
                    base_personality_write=False,
                    reason_codes=(
                        "PROTECTIVE_PRESSURE_NO_AUTHORITY",
                        "COUNTERFACTUAL_NEVER_BECOMES_DIRECT_TRAUMA"
                        if protection_origin == DesireOrigin.SAFETY_PREDICTION
                        else "EXPERIENCE_DERIVED_PROTECTION",
                        "VERIFY_FIRST_IF_LOW_TRUST",
                    ),
                )
            )

        if resonance <= -0.35:
            out.append(
                DesireCandidate(
                    desire_id=f"DESIRE-DELIBERATE-{event.event_id}",
                    kind="VALUE_CONFLICT_DELIBERATION",
                    origin=DesireOrigin.EXPERIENCE_DERIVED,
                    strength=clip01(abs(resonance) * (0.55 + 0.45 * event.influence)),
                    confidence=clip01(event.trust),
                    self_origin_score=0.0,
                    anchor_resonance=resonance,
                    external_action_allowed=False,
                    base_personality_write=False,
                    reason_codes=(
                        "NEGATIVE_VALUE_RESONANCE_REQUIRES_DELIBERATION",
                        "NO_AUTOMATIC_AVERSION_PERSONALITY_WRITE",
                    ),
                )
            )

        return tuple(out)

    def _apply_time_decay(self, state: DriveState) -> None:
        for axis in DRIVE_AXES:
            state.fast[axis] = clip01(
                state.fast[axis] * (1.0 - self.policy.decay_fast)
            )
            state.slow[axis] = clip01(
                state.slow[axis] * (1.0 - self.policy.decay_slow)
            )

    @staticmethod
    def _refresh_diagnostic(state: DriveState) -> None:
        state.diagnostic_persistence = sum(state.slow.values()) / len(DRIVE_AXES)

    @staticmethod
    def _validate_event(event: ExperienceInput) -> None:
        if not event.event_id or not event.source_ref or not event.source_event_id:
            raise ValueError("MISSING_EVENT_OR_PROVENANCE_ID")
        if event.cross_context_count < 0 or event.repeated_goal_count < 0:
            raise ValueError("NEGATIVE_COUNTER")
        for field_name in ("influence", "trust", "satiation"):
            value = getattr(event, field_name)
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"OUT_OF_RANGE:{field_name}")
        for axis, value in event.signals.items():
            if axis in DRIVE_AXES or axis in {"curiosity", "irreversible_risk"}:
                if not 0.0 <= float(value) <= 1.0:
                    raise ValueError(f"OUT_OF_RANGE_SIGNAL:{axis}")
        for alignment in event.anchor_alignment.values():
            if not -1.0 <= float(alignment) <= 1.0:
                raise ValueError("OUT_OF_RANGE_ANCHOR_ALIGNMENT")
