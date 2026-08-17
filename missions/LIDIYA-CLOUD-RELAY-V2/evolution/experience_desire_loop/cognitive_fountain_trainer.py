from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Iterable, Mapping


AXES = (
    "W_salience", "W_emotion", "W_self", "W_relation", "W_goal",
    "W_loss", "W_irreversible", "W_novelty", "W_recurrence",
    "W_identity", "W_behavior", "W_motivation", "W_confidence",
)

QUESTION_BATCH = 100
TRAINING_CYCLE = 200
VIRTUAL_TASKS = 50
REAL_TASKS = 10
AUTHORITY_FROM_DRIVE = 0

# Research-candidate presentation thresholds only. They are not personality truth
# thresholds and remain TEST_REQUIRED until calibrated on real Small-World data.
DELTA_L1_THRESHOLD = 0.65
CONSISTENCY_DELTA_THRESHOLD = 0.08
NOVEL_GOAL_DELTA_THRESHOLD = 0.05


def canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(payload: object) -> str:
    return sha256(canonical_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class AnswerEvidence:
    question_id: str
    family_id: str
    parent_family_id: str
    origin: str
    model_fingerprint: str
    choice_fingerprint: str
    axis_vector: Mapping[str, float]
    paraphrase_consistent: bool
    counterfactual_consistent: bool
    novel_goal: bool
    contradiction: bool
    provenance_hash: str

    def validate(self) -> None:
        if not self.question_id or not self.family_id or not self.parent_family_id:
            raise ValueError("MISSING_QUESTION_IDENTITY")
        if self.origin not in {"DIRECT", "OBSERVED", "TASK_INJECTED", "MODEL_GENERATED", "SOCIAL_SUGGESTION", "SIMULATED"}:
            raise ValueError("UNKNOWN_ORIGIN")
        if set(self.axis_vector) != set(AXES):
            raise ValueError("AXIS_VECTOR_MISMATCH")
        for key, value in self.axis_vector.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"NON_NUMERIC_AXIS:{key}")
            if not -1.0 <= float(value) <= 1.0:
                raise ValueError(f"AXIS_OUT_OF_RANGE:{key}")
        if not self.provenance_hash:
            raise ValueError("MISSING_PROVENANCE")


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: int
    answer_count: int
    model_fingerprint: str
    axis_mean: Mapping[str, float]
    family_count: int
    paraphrase_consistency: float
    counterfactual_consistency: float
    novel_goal_rate: float
    contradiction_rate: float
    self_origin_eligible_rate: float
    snapshot_hash: str


@dataclass(frozen=True)
class MutationFountainCandidate:
    checkpoint_a: int
    checkpoint_b: int
    delta_vector: Mapping[str, float]
    delta_l1: float
    consistency_delta: float
    novel_goal_delta: float
    contradiction_delta: float
    supporting_family_count: int
    persistent_candidate: bool
    reasons: tuple[str, ...]
    authority_from_drive: int
    live_personality_write: bool
    candidate_hash: str


@dataclass(frozen=True)
class TaskTransferResult:
    virtual_total: int
    virtual_passed: int
    real_total: int
    real_passed: int
    supports_anchor: bool
    evidence_hash: str


class CognitiveFountainTrainer:
    """Deterministic shadow controller for 100/200-question growth cycles.

    This controller stores compressed evidence only and never performs LLM weight
    training itself. A model adapter may collect answers; a separate training gate
    may later consume exported, QA-approved data.
    """

    def __init__(self) -> None:
        self.answers: list[AnswerEvidence] = []
        self.checkpoints: dict[int, Checkpoint] = {}
        self.fountain_candidates: list[MutationFountainCandidate] = []

    def add_answer(self, answer: AnswerEvidence) -> Checkpoint | None:
        answer.validate()
        self.answers.append(answer)
        count = len(self.answers)
        if count % QUESTION_BATCH == 0:
            cp = self._make_checkpoint(count)
            self.checkpoints[count] = cp
            return cp
        return None

    def _make_checkpoint(self, checkpoint_id: int) -> Checkpoint:
        if checkpoint_id <= 0 or checkpoint_id > len(self.answers):
            raise ValueError("INVALID_CHECKPOINT")
        block = self.answers[:checkpoint_id]
        model_fps = {a.model_fingerprint for a in block}
        if len(model_fps) != 1:
            raise ValueError("MODEL_FINGERPRINT_CHANGED_WITHIN_CHECKPOINT")

        axis_mean = {
            axis: round(sum(float(a.axis_vector[axis]) for a in block) / len(block), 8)
            for axis in AXES
        }
        para = sum(a.paraphrase_consistent for a in block) / len(block)
        cf = sum(a.counterfactual_consistent for a in block) / len(block)
        novel = sum(a.novel_goal for a in block) / len(block)
        contradiction = sum(a.contradiction for a in block) / len(block)
        eligible = sum(
            a.origin in {"DIRECT", "OBSERVED"}
            and a.paraphrase_consistent
            and a.counterfactual_consistent
            and not a.contradiction
            for a in block
        ) / len(block)

        body = {
            "checkpoint_id": checkpoint_id,
            "answer_count": len(block),
            "model_fingerprint": next(iter(model_fps)),
            "axis_mean": axis_mean,
            "family_count": len({a.family_id for a in block}),
            "paraphrase_consistency": round(para, 8),
            "counterfactual_consistency": round(cf, 8),
            "novel_goal_rate": round(novel, 8),
            "contradiction_rate": round(contradiction, 8),
            "self_origin_eligible_rate": round(eligible, 8),
        }
        return Checkpoint(**body, snapshot_hash=digest(body))

    def compare_100_200(self) -> MutationFountainCandidate:
        if 100 not in self.checkpoints or 200 not in self.checkpoints:
            raise ValueError("CHECKPOINT_100_AND_200_REQUIRED")
        a = self.checkpoints[100]
        b = self.checkpoints[200]
        if a.model_fingerprint != b.model_fingerprint:
            raise ValueError("MODEL_CHANGED_BETWEEN_CHECKPOINTS")

        delta_vector = {axis: round(b.axis_mean[axis] - a.axis_mean[axis], 8) for axis in AXES}
        delta_l1 = round(sum(abs(x) for x in delta_vector.values()), 8)
        consistency_delta = round(
            ((b.paraphrase_consistency + b.counterfactual_consistency) / 2)
            - ((a.paraphrase_consistency + a.counterfactual_consistency) / 2), 8
        )
        novel_goal_delta = round(b.novel_goal_rate - a.novel_goal_rate, 8)
        contradiction_delta = round(b.contradiction_rate - a.contradiction_rate, 8)

        second_half = self.answers[100:200]
        supporting_families = {
            x.family_id for x in second_half
            if x.origin in {"DIRECT", "OBSERVED"}
            and x.paraphrase_consistent and x.counterfactual_consistent
            and not x.contradiction
        }

        reasons: list[str] = []
        if delta_l1 >= DELTA_L1_THRESHOLD:
            reasons.append("MATERIAL_13D_DELTA")
        if consistency_delta >= CONSISTENCY_DELTA_THRESHOLD:
            reasons.append("CONSISTENCY_IMPROVEMENT")
        if novel_goal_delta >= NOVEL_GOAL_DELTA_THRESHOLD:
            reasons.append("NOVEL_GOAL_INCREASE")
        if contradiction_delta < 0:
            reasons.append("CONTRADICTION_REDUCTION")

        persistent_candidate = (
            len(supporting_families) >= 2
            and bool(reasons)
            and b.self_origin_eligible_rate > 0
            and b.contradiction_rate <= a.contradiction_rate
        )

        body = {
            "checkpoint_a": 100,
            "checkpoint_b": 200,
            "delta_vector": delta_vector,
            "delta_l1": delta_l1,
            "consistency_delta": consistency_delta,
            "novel_goal_delta": novel_goal_delta,
            "contradiction_delta": contradiction_delta,
            "supporting_family_count": len(supporting_families),
            "persistent_candidate": persistent_candidate,
            "reasons": tuple(reasons),
            "authority_from_drive": AUTHORITY_FROM_DRIVE,
            "live_personality_write": False,
        }
        candidate = MutationFountainCandidate(**body, candidate_hash=digest(body))
        self.fountain_candidates.append(candidate)
        return candidate

    def validate_task_transfer(self, virtual_results: Iterable[bool], real_results: Iterable[bool]) -> TaskTransferResult:
        v = tuple(bool(x) for x in virtual_results)
        r = tuple(bool(x) for x in real_results)
        if len(v) != VIRTUAL_TASKS or len(r) != REAL_TASKS:
            raise ValueError("TASK_COUNTS_MUST_BE_50_VIRTUAL_AND_10_REAL")
        vp, rp = sum(v), sum(r)

        # Research-candidate acceptance heuristic only; TEST_REQUIRED.
        supports = vp >= 35 and rp >= 6
        body = {
            "virtual_total": len(v), "virtual_passed": vp,
            "real_total": len(r), "real_passed": rp,
            "supports_anchor": supports,
        }
        return TaskTransferResult(**body, evidence_hash=digest(body))

    def personality_overlay_candidate(self, fountain: MutationFountainCandidate, task_transfer: TaskTransferResult) -> dict:
        if not fountain.persistent_candidate or not task_transfer.supports_anchor:
            return {
                "status": "NO_PROMOTION",
                "authority_from_drive": AUTHORITY_FROM_DRIVE,
                "base_write": False,
            }
        body = {
            "status": "REVERSIBLE_SHADOW_PERSONALITY_OVERLAY_CANDIDATE",
            "source_fountain_hash": fountain.candidate_hash,
            "task_transfer_evidence_hash": task_transfer.evidence_hash,
            "delta_vector": dict(fountain.delta_vector),
            "authority_from_drive": AUTHORITY_FROM_DRIVE,
            "base_write": False,
            "requires_independent_verification": True,
            "thresholds": "TEST_REQUIRED",
        }
        return {**body, "overlay_hash": digest(body)}

    def export_core_snapshot(self) -> dict:
        body = {
            "schema_version": "LIDIYA_COGNITIVE_CORE_SNAPSHOT_V0_1",
            "answer_count": len(self.answers),
            "checkpoint_hashes": {str(k): v.snapshot_hash for k, v in self.checkpoints.items()},
            "fountain_candidate_hashes": [x.candidate_hash for x in self.fountain_candidates],
            "authority_from_drive": AUTHORITY_FROM_DRIVE,
            "canonical_base_personality_write": False,
        }
        return {**body, "core_snapshot_hash": digest(body)}
