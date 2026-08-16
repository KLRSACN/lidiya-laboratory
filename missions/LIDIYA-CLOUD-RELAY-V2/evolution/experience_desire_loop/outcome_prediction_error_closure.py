from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Tuple


class OutcomeNamespace(str, Enum):
    AUTOBIOGRAPHICAL = "AUTOBIOGRAPHICAL"
    MODEL_LEARNED_SLOW_PLANNING = "MODEL_LEARNED_SLOW_PLANNING"


def clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def clip11(value: float) -> float:
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
class Prediction:
    prediction_id: str
    goal_id: str
    expected_value: float
    expected_harm: float
    confidence: float
    provenance: str
    evidence_set_hash: str


@dataclass(frozen=True)
class AppraisalAcceptanceReceipt:
    """Structured shadow receipt for a previously derived appraisal.

    This is a deterministic research binding, not a cryptographic or formal trust
    authority. It replaces the legacy producer-supplied independently_verified
    boolean in Outcome Closure. Exact acceptance/signing semantics remain
    TEST_REQUIRED until a formal integration gate is defined.
    """

    appraisal_id: str
    appraisal_fingerprint: str
    source_event_hash: str
    verifier_envelope_hash: str
    appraisal_policy_hash: str
    anchor_registry_hash: str
    trust_eligibility: bool
    acceptance_route: str
    receipt_hash: str

    @classmethod
    def build(
        cls,
        *,
        appraisal_id: str,
        appraisal_fingerprint: str,
        source_event_hash: str,
        verifier_envelope_hash: str,
        appraisal_policy_hash: str,
        anchor_registry_hash: str,
        trust_eligibility: bool,
        acceptance_route: str,
    ) -> "AppraisalAcceptanceReceipt":
        payload = {
            "appraisal_id": appraisal_id,
            "appraisal_fingerprint": appraisal_fingerprint,
            "source_event_hash": source_event_hash,
            "verifier_envelope_hash": verifier_envelope_hash,
            "appraisal_policy_hash": appraisal_policy_hash,
            "anchor_registry_hash": anchor_registry_hash,
            "trust_eligibility": bool(trust_eligibility),
            "acceptance_route": acceptance_route,
        }
        return cls(**payload, receipt_hash=canonical_hash(payload))

    def validate(self) -> bool:
        if not all(
            (
                self.appraisal_id,
                self.appraisal_fingerprint,
                self.source_event_hash,
                self.verifier_envelope_hash,
                self.appraisal_policy_hash,
                self.anchor_registry_hash,
                self.acceptance_route,
                self.receipt_hash,
            )
        ):
            return False
        payload = {
            "appraisal_id": self.appraisal_id,
            "appraisal_fingerprint": self.appraisal_fingerprint,
            "source_event_hash": self.source_event_hash,
            "verifier_envelope_hash": self.verifier_envelope_hash,
            "appraisal_policy_hash": self.appraisal_policy_hash,
            "anchor_registry_hash": self.anchor_registry_hash,
            "trust_eligibility": bool(self.trust_eligibility),
            "acceptance_route": self.acceptance_route,
        }
        return self.receipt_hash == canonical_hash(payload)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    goal_id: str
    observed_value: float
    observed_harm: float
    provenance: str
    source_event_hash: str
    appraisal_receipt: AppraisalAcceptanceReceipt | None


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


def _validated_appraisal_binding(observation: Observation) -> bool:
    receipt = observation.appraisal_receipt
    return bool(
        receipt is not None
        and receipt.validate()
        and receipt.trust_eligibility
        and receipt.source_event_hash == observation.source_event_hash
    )


def close_outcome(prediction: Prediction, observation: Observation) -> OutcomeClosure:
    """Close one prediction against one observed result.

    Shadow deterministic reference only. It never writes base Personality and never
    grants external-action authority. DIRECT observations may become autobiographical
    candidates only when they carry a valid structured appraisal receipt bound to
    the same source event. Missing/invalid receipts remain planning-only.
    """
    if prediction.goal_id != observation.goal_id:
        raise ValueError("GOAL_MISMATCH")
    if not prediction.prediction_id or not observation.observation_id:
        raise ValueError("MISSING_ID")
    if not prediction.evidence_set_hash or not observation.source_event_hash:
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

    appraisal_bound = _validated_appraisal_binding(observation)
    if not appraisal_bound:
        namespace = OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING
        autobiographical = False
        reasons = ("APPRAISAL_BINDING_INVALID_OR_INELIGIBLE", "PLANNING_ONLY")
    elif observation.provenance == "DIRECT":
        namespace = OutcomeNamespace.AUTOBIOGRAPHICAL
        autobiographical = True
        reasons = ("DIRECT_APPRAISAL_BOUND_OUTCOME", "OUTCOME_CLOSURE")
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

    receipt_hash = (
        observation.appraisal_receipt.receipt_hash
        if observation.appraisal_receipt is not None
        else "NO_APPRAISAL_RECEIPT"
    )
    closure_seed = "|".join(
        (
            prediction.prediction_id,
            observation.observation_id,
            prediction.evidence_set_hash,
            observation.source_event_hash,
            receipt_hash,
        )
    )
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
