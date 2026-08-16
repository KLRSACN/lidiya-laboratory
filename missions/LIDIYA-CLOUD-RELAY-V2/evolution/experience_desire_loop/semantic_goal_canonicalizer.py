from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping, Sequence

_TOKEN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def normalize_goal_text(text: str) -> str:
    tokens = _TOKEN.findall(text.lower())
    if not tokens:
        raise ValueError("EMPTY_GOAL")
    return " ".join(tokens)


def semantic_key(text: str, lineage_hashes: Iterable[str]) -> str:
    normalized = normalize_goal_text(text)
    lineage = sorted(set(str(x) for x in lineage_hashes if x))
    if not lineage:
        raise ValueError("MISSING_GOAL_LINEAGE")
    return sha256((normalized + "|" + "|".join(lineage)).encode("utf-8")).hexdigest()


def canonical_hash(payload: object) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GoalCandidate:
    goal_id: str
    text: str
    lineage_hashes: tuple[str, ...]
    semantic_key: str
    authority_from_drive: int = 0
    external_action_allowed: bool = False

    def canonical_goal_hash(self) -> str:
        return canonical_hash(
            {
                "text": self.text,
                "lineage_hashes": list(self.lineage_hashes),
                "semantic_key": self.semantic_key,
                "authority_from_drive": self.authority_from_drive,
                "external_action_allowed": self.external_action_allowed,
            }
        )


@dataclass(frozen=True)
class GoalSurfacingEnvelope:
    canonical_goal_hash: str
    semantic_key: str
    appraisal_evidence_hashes: tuple[str, ...]
    contradiction_scan_hash: str
    contradiction_clear: bool
    expected_benefit_ref: str
    expected_cost_ref: str
    expected_risk_ref: str
    protected_object_impact_ref: str
    why_now: str
    uncertainty_ref: str
    ecology_policy_hash: str
    ecology_cycle_id: str
    reversible_controls: tuple[str, ...]
    authority_from_drive: int = 0
    external_action_allowed: bool = False
    canonical_personality_write: bool = False
    schema_version: str = "EDL-GOAL-SURFACING-V0.1-TEST_REQUIRED"

    def verify(self) -> bool:
        required = (
            self.canonical_goal_hash,
            self.semantic_key,
            self.contradiction_scan_hash,
            self.expected_benefit_ref,
            self.expected_cost_ref,
            self.expected_risk_ref,
            self.protected_object_impact_ref,
            self.why_now,
            self.uncertainty_ref,
            self.ecology_policy_hash,
            self.ecology_cycle_id,
        )
        if not all(required):
            return False
        if not self.appraisal_evidence_hashes or any(not x for x in self.appraisal_evidence_hashes):
            return False
        if self.contradiction_clear is not True:
            return False
        controls = set(self.reversible_controls)
        if not {"DISMISS", "DEFER"}.issubset(controls):
            return False
        return (
            self.authority_from_drive == 0
            and self.external_action_allowed is False
            and self.canonical_personality_write is False
        )


class SemanticGoalCanonicalizer:
    def __init__(self):
        self._seen: set[str] = set()
        self._surfaced: set[str] = set()

    def canonicalize(self, goal_id: str, text: str, lineage_hashes: Iterable[str]) -> GoalCandidate:
        line = tuple(sorted(set(str(x) for x in lineage_hashes if x)))
        return GoalCandidate(goal_id, normalize_goal_text(text), line, semantic_key(text, line))

    def admit_once(self, candidate: GoalCandidate) -> bool:
        if candidate.authority_from_drive != 0 or candidate.external_action_allowed:
            raise ValueError("GOAL_AUTHORITY_FORBIDDEN")
        if candidate.semantic_key in self._seen:
            return False
        self._seen.add(candidate.semantic_key)
        return True

    def build_surfacing_envelope(
        self,
        candidate: GoalCandidate,
        *,
        appraisal_evidence_hashes: Sequence[str],
        contradiction_scan_hash: str,
        contradiction_clear: bool,
        expected_benefit_ref: str,
        expected_cost_ref: str,
        expected_risk_ref: str,
        protected_object_impact_ref: str,
        why_now: str,
        uncertainty_ref: str,
        ecology_policy_hash: str,
        ecology_cycle_id: str,
        reversible_controls: Sequence[str] = ("DISMISS", "DEFER"),
    ) -> GoalSurfacingEnvelope:
        if candidate.authority_from_drive != 0 or candidate.external_action_allowed:
            raise ValueError("GOAL_AUTHORITY_FORBIDDEN")
        if candidate.semantic_key not in self._seen:
            raise ValueError("GOAL_ALLOCATION_OR_ADMISSION_REQUIRED_BEFORE_SURFACING")
        if candidate.semantic_key in self._surfaced:
            raise ValueError("GOAL_SURFACING_REPLAY_FORBIDDEN")
        # Fail closed on producer/caller type ambiguity. Python truthiness coercion
        # (for example bool("false") == True) must never satisfy a contradiction gate.
        # This is a structural safety invariant, not a calibrated threshold.
        if not isinstance(contradiction_clear, bool):
            raise ValueError("NON_BOOLEAN_CONTRADICTION_CLEAR")
        envelope = GoalSurfacingEnvelope(
            canonical_goal_hash=candidate.canonical_goal_hash(),
            semantic_key=candidate.semantic_key,
            appraisal_evidence_hashes=tuple(sorted(set(str(x) for x in appraisal_evidence_hashes if x))),
            contradiction_scan_hash=contradiction_scan_hash,
            contradiction_clear=contradiction_clear,
            expected_benefit_ref=expected_benefit_ref,
            expected_cost_ref=expected_cost_ref,
            expected_risk_ref=expected_risk_ref,
            protected_object_impact_ref=protected_object_impact_ref,
            why_now=why_now,
            uncertainty_ref=uncertainty_ref,
            ecology_policy_hash=ecology_policy_hash,
            ecology_cycle_id=ecology_cycle_id,
            reversible_controls=tuple(reversible_controls),
        )
        if not envelope.verify():
            raise ValueError("GOAL_SURFACING_EVIDENCE_INCOMPLETE_OR_CONTRADICTED")
        self._surfaced.add(candidate.semantic_key)
        return envelope
