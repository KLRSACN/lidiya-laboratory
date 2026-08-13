from __future__ import annotations

from dataclasses import dataclass, field, asdict
from hashlib import sha256
import json
from typing import Any, Dict, Iterable, List, Mapping, Sequence

WEIGHT_DIMENSIONS = (
    "W_salience", "W_emotion", "W_self", "W_relation", "W_goal", "W_loss",
    "W_irreversible", "W_novelty", "W_recurrence", "W_identity", "W_behavior",
    "W_motivation", "W_confidence",
)

PROTECTED_DOMAINS = {"Identity", "Personality", "Governance"}


def _bounded(value: float, low: float = 0.0, high: float = 1.0) -> float:
    value = float(value)
    if not low <= value <= high:
        raise ValueError(f"value {value} outside [{low}, {high}]")
    return value


@dataclass(frozen=True)
class MemoryWeights:
    W_salience: float = 0.0
    W_emotion: float = 0.0
    W_self: float = 0.0
    W_relation: float = 0.0
    W_goal: float = 0.0
    W_loss: float = 0.0
    W_irreversible: float = 0.0
    W_novelty: float = 0.0
    W_recurrence: float = 0.0
    W_identity: float = 0.0
    W_behavior: float = 0.0
    W_motivation: float = 0.0
    W_confidence: float = 1.0

    def __post_init__(self) -> None:
        for name in WEIGHT_DIMENSIONS:
            _bounded(getattr(self, name))

    def as_dict(self) -> Dict[str, float]:
        return {name: getattr(self, name) for name in WEIGHT_DIMENSIONS}


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    timestamp: str
    event_summary: str
    entities: Sequence[str] = field(default_factory=tuple)
    source: str = "UNKNOWN"
    evidence: Sequence[str] = field(default_factory=tuple)
    confidence: float = 0.5
    salience: float = 0.0
    valence: float = 0.0
    arousal: float = 0.0
    self_relevance: float = 0.0
    relationship_relevance: float = 0.0
    goal_relevance: float = 0.0
    loss_risk: float = 0.0
    irreversibility: float = 0.0
    agency_score: float = 0.0
    responsibility_score: float = 0.0
    surprise: float = 0.0
    prediction_error: float = 0.0
    competence_gap: float = 0.0
    trust_delta: float = 0.0
    attachment_delta: float = 0.0
    self_preservation_delta: float = 0.0
    personality_impacts: Mapping[str, float] = field(default_factory=dict)
    linked_memories: Sequence[str] = field(default_factory=tuple)
    lessons_learned: str = ""
    self_reflection: str = ""
    behavioral_principle: str = ""
    unresolved_need: str = ""
    generated_motivation: str = ""
    generated_goal: str = ""
    update_history: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    weights: MemoryWeights = field(default_factory=MemoryWeights)

    def __post_init__(self) -> None:
        for name in (
            "confidence", "salience", "arousal", "self_relevance", "relationship_relevance",
            "goal_relevance", "loss_risk", "irreversibility", "agency_score",
            "responsibility_score", "surprise", "prediction_error", "competence_gap",
        ):
            _bounded(getattr(self, name))
        _bounded(self.valence, -1.0, 1.0)
        for name in ("trust_delta", "attachment_delta", "self_preservation_delta"):
            _bounded(getattr(self, name), -1.0, 1.0)
        for value in self.personality_impacts.values():
            _bounded(value, -1.0, 1.0)

    def canonical_payload(self) -> Dict[str, Any]:
        data = asdict(self)
        data["entities"] = list(self.entities)
        data["evidence"] = list(self.evidence)
        data["linked_memories"] = list(self.linked_memories)
        data["update_history"] = list(self.update_history)
        return data

    def fingerprint(self) -> str:
        raw = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(raw.encode("utf-8")).hexdigest()


def retrieval_score(weights: MemoryWeights, context: Mapping[str, float] | None = None) -> float:
    """Compute retrieval priority without destroying original multi-dimensional weights."""
    context = context or {}
    numerator = 0.0
    denominator = 0.0
    for name, value in weights.as_dict().items():
        importance = _bounded(context.get(name, 1.0))
        numerator += value * importance
        denominator += importance
    return numerator / denominator if denominator else 0.0


def append_update(record: MemoryRecord, update: Mapping[str, Any]) -> MemoryRecord:
    """Append-only audit history: prior entries are never rewritten."""
    payload = record.canonical_payload()
    payload["update_history"] = tuple(list(record.update_history) + [dict(update)])
    payload["weights"] = record.weights
    return MemoryRecord(**payload)


def bounded_associative_activation(
    seed_ids: Iterable[str],
    records: Mapping[str, MemoryRecord],
    *,
    max_depth: int = 2,
    max_nodes: int = 12,
    decay: float = 0.65,
) -> List[Dict[str, Any]]:
    """Bounded graph spread. Recurrence alone cannot dominate identity/meaning."""
    if max_depth < 0 or max_nodes <= 0:
        return []
    decay = _bounded(decay)
    queue: List[tuple[str, int, float]] = [(mid, 0, 1.0) for mid in seed_ids]
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    while queue and len(out) < max_nodes:
        memory_id, depth, inherited = queue.pop(0)
        if memory_id in seen or memory_id not in records or depth > max_depth:
            continue
        seen.add(memory_id)
        record = records[memory_id]
        w = record.weights
        meaning = (
            0.22 * w.W_identity + 0.18 * w.W_self + 0.16 * w.W_goal + 0.14 * w.W_loss
            + 0.10 * w.W_relation + 0.08 * w.W_emotion + 0.07 * w.W_salience
            + 0.03 * w.W_novelty + 0.02 * w.W_recurrence
        )
        activation = inherited * meaning
        out.append({"memory_id": memory_id, "depth": depth, "activation": round(activation, 8)})
        if depth < max_depth:
            for child in record.linked_memories:
                if child not in seen:
                    queue.append((child, depth + 1, inherited * decay))
    out.sort(key=lambda item: (-item["activation"], item["memory_id"]))
    return out
