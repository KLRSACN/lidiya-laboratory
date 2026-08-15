from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Tuple


class OutcomeNamespace(str, Enum):
    AUTOBIOGRAPHICAL = "AUTOBIOGRAPHICAL"
    MODEL_LEARNED_SLOW_PLANNING = "MODEL_LEARNED_SLOW_PLANNING"


def clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def clip11(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


@dataclass(frozen=True)
class Prediction:
    prediction_id: str
    goal_id: str
    expected_value: float
    expected_harm: float
    confidence: float
    provenance: str
    evidence_set_hash: str


@dataclass(frozen=True)
class Observation:
    observation_id: str
    goal_id: str
    observed_value: float
    observed_harm: float
    provenance: str
    verifier_envelope_hash: str
    independently_verified: bool


@dataclass(frozen=True)
class OutcomeClosure:
    closure_id: str
    goal_id: str
    value_error: float
    harm_error: float
    total_error: float
    direction: str
    target_namespace: OutcomeNamespace
    planning_delta_candidate: float
    autobiographical_experience_eligible: bool
    base_personality_write: bool
    external_action_authority: int
    reason_codes: Tuple[str, ...]


def close_outcome(prediction: Prediction, observation: Observation) -> OutcomeClosure:
    """Close one prediction against one observed result.

    This is a shadow deterministic reference. It never writes base Personality and
    never grants external action authority. DIRECT + independently verified outcomes
    may become autobiographical experience candidates. Simulated/non-direct outcomes
    remain in MODEL_LEARNED_SLOW_PLANNING.
    """
    if prediction.goal_id != observation.goal_id:
        raise ValueError("GOAL_MISMATCH")
    if not prediction.prediction_id or not observation.observation_id:
        raise ValueError("MISSING_ID")
    if not prediction.evidence_set_hash or not observation.verifier_envelope_hash:
        raise ValueError("MISSING_EVIDENCE_BINDING")

    for name, value in (
        ("expected_value", prediction.expected_value),
        ("expected_harm", prediction.expected_harm),
        ("confidence", prediction.confidence),
        ("observed_value", observation.observed_value),
        ("observed_harm", observation.observed_harm),
    ):
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"OUT_OF_RANGE:{name}")

    value_error = clip11(observation.observed_value - prediction.expected_value)
    harm_error = clip11(observation.observed_harm - prediction.expected_harm)
    total_error = clip01((abs(value_error) + abs(harm_error)) / 2.0)

    if not observation.independently_verified:
        namespace = OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING
        autobiographical = False
        reasons = ("OBSERVATION_NOT_INDEPENDENTLY_VERIFIED", "PLANNING_ONLY")
    elif observation.provenance == "DIRECT":
        namespace = OutcomeNamespace.AUTOBIOGRAPHICAL
        autobiographical = True
        reasons = ("DIRECT_VERIFIED_OUTCOME", "OUTCOME_CLOSURE")
    else:
        namespace = OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING
        autobiographical = False
        reasons = ("NON_DIRECT_OUTCOME", "PLANNING_ONLY")

    if harm_error > 0.10:
        direction = "INCREASE_CAUTION"
        planning_delta = clip11(harm_error * (0.5 + 0.5 * clip01(prediction.confidence)))
    elif harm_error < -0.10:
        direction = "DECREASE_CAUTION_CANDIDATE"
        planning_delta = clip11(harm_error * (0.5 + 0.5 * clip01(prediction.confidence)))
    elif value_error > 0.10:
        direction = "INCREASE_EXPECTED_VALUE"
        planning_delta = clip11(value_error * 0.5)
    elif value_error < -0.10:
        direction = "DECREASE_EXPECTED_VALUE"
        planning_delta = clip11(value_error * 0.5)
    else:
        direction = "CONFIRM_MODEL"
        planning_delta = 0.0

    closure_seed = "|".join((
        prediction.prediction_id,
        observation.observation_id,
        prediction.evidence_set_hash,
        observation.verifier_envelope_hash,
    ))
    closure_id = sha256(closure_seed.encode("utf-8")).hexdigest()[:16]

    return OutcomeClosure(
        closure_id=closure_id,
        goal_id=prediction.goal_id,
        value_error=value_error,
        harm_error=harm_error,
        total_error=total_error,
        direction=direction,
        target_namespace=namespace,
        planning_delta_candidate=planning_delta,
        autobiographical_experience_eligible=autobiographical,
        base_personality_write=False,
        external_action_authority=0,
        reason_codes=reasons,
    )
