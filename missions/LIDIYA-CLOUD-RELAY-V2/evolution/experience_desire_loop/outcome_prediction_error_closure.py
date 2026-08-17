from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Mapping, Tuple


class OutcomeNamespace(str, Enum):
    AUTOBIOGRAPHICAL = "AUTOBIOGRAPHICAL"
    MODEL_LEARNED_SLOW_PLANNING = "MODEL_LEARNED_SLOW_PLANNING"


class AcceptanceRoute(str, Enum):
    LIVE_SHADOW_APPRAISAL_CHOKE_POINT_V0_1 = "LIVE_SHADOW_APPRAISAL_CHOKE_POINT_V0.1"


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
class AppraisalAcceptanceRecord:
    """Append-only acceptance record produced outside Outcome Closure.

    The trusted storage/provider semantics that make a snapshot authoritative are
    deliberately external and remain TEST_REQUIRED. Outcome Closure only accepts
    a record that is present in an explicitly pinned snapshot and matches every
    receipt/ref field exactly.
    """

    acceptance_record_id: str
    appraisal_id: str
    appraisal_fingerprint: str
    source_event_hash: str
    verifier_envelope_hash: str
    appraisal_policy_hash: str
    anchor_registry_hash: str
    issuer_registry_id: str
    installation_id: str
    workspace_identity: str
    trust_eligibility: bool
    acceptance_route: AcceptanceRoute
    revoked: bool = False

    @property
    def record_hash(self) -> str:
        return canonical_hash(
            {
                "acceptance_record_id": self.acceptance_record_id,
                "appraisal_id": self.appraisal_id,
                "appraisal_fingerprint": self.appraisal_fingerprint,
                "source_event_hash": self.source_event_hash,
                "verifier_envelope_hash": self.verifier_envelope_hash,
                "appraisal_policy_hash": self.appraisal_policy_hash,
                "anchor_registry_hash": self.anchor_registry_hash,
                "issuer_registry_id": self.issuer_registry_id,
                "installation_id": self.installation_id,
                "workspace_identity": self.workspace_identity,
                "trust_eligibility": bool(self.trust_eligibility),
                "acceptance_route": self.acceptance_route.value,
                "revoked": bool(self.revoked),
            }
        )


@dataclass(frozen=True)
class AcceptanceRegistrySnapshot:
    registry_id: str
    installation_id: str
    workspace_identity: str
    records: Tuple[AppraisalAcceptanceRecord, ...]

    @property
    def snapshot_hash(self) -> str:
        ordered = sorted(record.record_hash for record in self.records)
        return canonical_hash(
            {
                "registry_id": self.registry_id,
                "installation_id": self.installation_id,
                "workspace_identity": self.workspace_identity,
                "record_hashes": ordered,
            }
        )

    def resolve(self, acceptance_record_id: str) -> AppraisalAcceptanceRecord | None:
        matches = [r for r in self.records if r.acceptance_record_id == acceptance_record_id]
        if len(matches) != 1:
            return None
        return matches[0]


@dataclass(frozen=True)
class TrustedAcceptanceContext:
    """Pinned integration context supplied by the trusted host boundary.

    This object models the integration contract only. How these values are
    installed, signed, rotated, persisted and rollback-protected is TEST_REQUIRED.
    """

    expected_registry_id: str
    expected_registry_snapshot_hash: str
    expected_installation_id: str
    expected_workspace_identity: str
    allowed_verifier_envelope_hashes: Tuple[str, ...]
    allowed_appraisal_policy_hashes: Tuple[str, ...]
    allowed_anchor_registry_hashes: Tuple[str, ...]


@dataclass(frozen=True)
class AppraisalAcceptanceReceipt:
    appraisal_id: str
    appraisal_fingerprint: str
    source_event_hash: str
    verifier_envelope_hash: str
    appraisal_policy_hash: str
    anchor_registry_hash: str
    trust_eligibility: bool
    acceptance_route: AcceptanceRoute
    acceptance_record_id: str
    issuer_registry_id: str
    installation_id: str
    workspace_identity: str
    acceptance_record_hash: str
    receipt_hash: str

    @classmethod
    def from_record(cls, record: AppraisalAcceptanceRecord) -> "AppraisalAcceptanceReceipt":
        payload = {
            "appraisal_id": record.appraisal_id,
            "appraisal_fingerprint": record.appraisal_fingerprint,
            "source_event_hash": record.source_event_hash,
            "verifier_envelope_hash": record.verifier_envelope_hash,
            "appraisal_policy_hash": record.appraisal_policy_hash,
            "anchor_registry_hash": record.anchor_registry_hash,
            "trust_eligibility": bool(record.trust_eligibility),
            "acceptance_route": record.acceptance_route.value,
            "acceptance_record_id": record.acceptance_record_id,
            "issuer_registry_id": record.issuer_registry_id,
            "installation_id": record.installation_id,
            "workspace_identity": record.workspace_identity,
            "acceptance_record_hash": record.record_hash,
        }
        return cls(
            appraisal_id=record.appraisal_id,
            appraisal_fingerprint=record.appraisal_fingerprint,
            source_event_hash=record.source_event_hash,
            verifier_envelope_hash=record.verifier_envelope_hash,
            appraisal_policy_hash=record.appraisal_policy_hash,
            anchor_registry_hash=record.anchor_registry_hash,
            trust_eligibility=record.trust_eligibility,
            acceptance_route=record.acceptance_route,
            acceptance_record_id=record.acceptance_record_id,
            issuer_registry_id=record.issuer_registry_id,
            installation_id=record.installation_id,
            workspace_identity=record.workspace_identity,
            acceptance_record_hash=record.record_hash,
            receipt_hash=canonical_hash(payload),
        )

    def validate_self_consistency(self) -> bool:
        if not all(
            (
                self.appraisal_id,
                self.appraisal_fingerprint,
                self.source_event_hash,
                self.verifier_envelope_hash,
                self.appraisal_policy_hash,
                self.anchor_registry_hash,
                self.acceptance_record_id,
                self.issuer_registry_id,
                self.installation_id,
                self.workspace_identity,
                self.acceptance_record_hash,
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
            "acceptance_route": self.acceptance_route.value,
            "acceptance_record_id": self.acceptance_record_id,
            "issuer_registry_id": self.issuer_registry_id,
            "installation_id": self.installation_id,
            "workspace_identity": self.workspace_identity,
            "acceptance_record_hash": self.acceptance_record_hash,
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


def _validated_appraisal_binding(
    observation: Observation,
    *,
    acceptance_registry: AcceptanceRegistrySnapshot | None,
    trusted_acceptance_context: TrustedAcceptanceContext | None,
) -> bool:
    receipt = observation.appraisal_receipt
    registry = acceptance_registry
    trusted = trusted_acceptance_context
    if receipt is None or registry is None or trusted is None:
        return False
    if not receipt.validate_self_consistency():
        return False
    if registry.registry_id != trusted.expected_registry_id:
        return False
    if registry.snapshot_hash != trusted.expected_registry_snapshot_hash:
        return False
    if registry.installation_id != trusted.expected_installation_id:
        return False
    if registry.workspace_identity != trusted.expected_workspace_identity:
        return False
    if receipt.issuer_registry_id != trusted.expected_registry_id:
        return False
    if receipt.installation_id != trusted.expected_installation_id:
        return False
    if receipt.workspace_identity != trusted.expected_workspace_identity:
        return False
    if receipt.verifier_envelope_hash not in trusted.allowed_verifier_envelope_hashes:
        return False
    if receipt.appraisal_policy_hash not in trusted.allowed_appraisal_policy_hashes:
        return False
    if receipt.anchor_registry_hash not in trusted.allowed_anchor_registry_hashes:
        return False
    if receipt.source_event_hash != observation.source_event_hash:
        return False

    record = registry.resolve(receipt.acceptance_record_id)
    if record is None or record.revoked or not record.trust_eligibility:
        return False
    if record.record_hash != receipt.acceptance_record_hash:
        return False
    if record.acceptance_route != receipt.acceptance_route:
        return False

    exact_pairs = (
        (record.appraisal_id, receipt.appraisal_id),
        (record.appraisal_fingerprint, receipt.appraisal_fingerprint),
        (record.source_event_hash, receipt.source_event_hash),
        (record.verifier_envelope_hash, receipt.verifier_envelope_hash),
        (record.appraisal_policy_hash, receipt.appraisal_policy_hash),
        (record.anchor_registry_hash, receipt.anchor_registry_hash),
        (record.issuer_registry_id, receipt.issuer_registry_id),
        (record.installation_id, receipt.installation_id),
        (record.workspace_identity, receipt.workspace_identity),
    )
    return bool(receipt.trust_eligibility and all(a == b for a, b in exact_pairs))


def close_outcome(
    prediction: Prediction,
    observation: Observation,
    *,
    acceptance_registry: AcceptanceRegistrySnapshot | None = None,
    trusted_acceptance_context: TrustedAcceptanceContext | None = None,
) -> OutcomeClosure:
    """Close one prediction against one observed result.

    Shadow deterministic reference only. It never writes base Personality and never
    grants external-action authority. DIRECT observations may become autobiographical
    candidates only when an exact receipt is resolved against a pinned acceptance
    registry snapshot and trusted integration context. Missing, forged, revoked,
    replayed, unrecognized or internally inconsistent receipts remain planning-only.
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

    appraisal_bound = _validated_appraisal_binding(
        observation,
        acceptance_registry=acceptance_registry,
        trusted_acceptance_context=trusted_acceptance_context,
    )
    if not appraisal_bound:
        namespace = OutcomeNamespace.MODEL_LEARNED_SLOW_PLANNING
        autobiographical = False
        reasons = ("APPRAISAL_ACCEPTANCE_REGISTRY_UNVERIFIED", "PLANNING_ONLY")
    elif observation.provenance == "DIRECT":
        namespace = OutcomeNamespace.AUTOBIOGRAPHICAL
        autobiographical = True
        reasons = ("DIRECT_REGISTRY_BOUND_APPRAISAL_OUTCOME", "OUTCOME_CLOSURE")
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
    registry_hash = acceptance_registry.snapshot_hash if acceptance_registry is not None else "NO_REGISTRY"
    closure_seed = "|".join(
        (
            prediction.prediction_id,
            observation.observation_id,
            prediction.evidence_set_hash,
            observation.source_event_hash,
            receipt_hash,
            registry_hash,
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
