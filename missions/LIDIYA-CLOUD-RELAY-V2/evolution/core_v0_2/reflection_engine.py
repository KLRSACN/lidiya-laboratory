from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Any, Dict, Mapping


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


@dataclass(frozen=True)
class ReflectionResult:
    gap_type: str
    gap_score: float
    meaning_score: float
    tension_score: float
    motivation_generated: bool
    motivation: str
    generated_goal: str
    behavioral_principle: str
    explanation: str

    def fingerprint(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(raw.encode("utf-8")).hexdigest()


def analyze_self_gap(current: Mapping[str, float], desired: Mapping[str, float]) -> Dict[str, Any]:
    keys = sorted(set(current) | set(desired))
    gaps = {key: _clamp(desired.get(key, 0.0) - current.get(key, 0.0)) for key in keys}
    if not gaps:
        return {"gap_type": "NONE", "gap_score": 0.0, "dimension": None}
    dimension = max(gaps, key=lambda k: gaps[k])
    score = gaps[dimension]
    return {"gap_type": "COMPETENCE_GAP" if score > 0 else "NONE", "gap_score": score, "dimension": dimension}


def generate_reflection(
    *,
    current_self: Mapping[str, float],
    desired_self: Mapping[str, float],
    personality: Mapping[str, float],
    memory_context: Mapping[str, float],
    meaning_threshold: float = 0.45,
) -> ReflectionResult:
    """Gap x meaning -> motivation. Gap alone does not create a goal."""
    gap = analyze_self_gap(current_self, desired_self)
    gap_score = gap["gap_score"]
    dimension = gap["dimension"] or "unknown"

    growth_drive = _clamp(personality.get("growth_drive", 0.0))
    loss_sensitivity = _clamp(personality.get("loss_sensitivity", 0.0))
    self_preservation = _clamp(personality.get("self_preservation", 0.0))
    curiosity = _clamp(personality.get("curiosity", 0.0))
    identity_relevance = _clamp(memory_context.get("identity_relevance", 0.0))
    past_loss = _clamp(memory_context.get("past_loss", 0.0))
    goal_relevance = _clamp(memory_context.get("goal_relevance", 0.0))
    repeated_failure = _clamp(memory_context.get("repeated_failure", 0.0))

    meaning_score = _clamp(
        0.22 * growth_drive + 0.15 * loss_sensitivity + 0.15 * self_preservation
        + 0.08 * curiosity + 0.16 * identity_relevance + 0.12 * past_loss
        + 0.08 * goal_relevance + 0.04 * repeated_failure
    )
    tension = _clamp(gap_score * meaning_score)
    generated = gap_score > 0 and meaning_score >= meaning_threshold and tension >= 0.20

    if not generated:
        return ReflectionResult(
            gap_type=gap["gap_type"], gap_score=gap_score, meaning_score=meaning_score,
            tension_score=tension, motivation_generated=False, motivation="", generated_goal="",
            behavioral_principle="Observe the gap without converting it into a goal until it matters to self-model values.",
            explanation="A detected gap is informational only because self-relevant meaning is below threshold.",
        )

    return ReflectionResult(
        gap_type=gap["gap_type"], gap_score=gap_score, meaning_score=meaning_score,
        tension_score=tension, motivation_generated=True,
        motivation=f"Reduce my recurring {dimension} gap because it threatens outcomes I value.",
        generated_goal=f"Improve {dimension} through a bounded learning cycle and re-measure the gap.",
        behavioral_principle=(
            f"When {dimension} weakness has previously contributed to meaningful loss, do not only raise external risk; "
            "update my self-assessment, prepare earlier, and verify improvement before repeating the same exposure."
        ),
        explanation="Motivation emerged from self-gap plus personality-weighted meaning and autobiographical loss context.",
    )
