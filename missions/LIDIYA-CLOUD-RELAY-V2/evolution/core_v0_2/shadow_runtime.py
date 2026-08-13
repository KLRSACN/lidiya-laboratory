from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any, Dict, Mapping

from .memory_model import PROTECTED_DOMAINS, MemoryRecord
from .reflection_engine import generate_reflection


class ProtectedMutationError(RuntimeError):
    pass


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def assert_shadow_mutation_scope(requested_domains: list[str] | tuple[str, ...]) -> None:
    blocked = PROTECTED_DOMAINS.intersection(requested_domains)
    if blocked:
        raise ProtectedMutationError(f"shadow candidate cannot mutate protected live domains: {sorted(blocked)}")


def shadow_evaluate(
    *,
    memory: MemoryRecord,
    live_self_model: Mapping[str, float],
    desired_self_model: Mapping[str, float],
    personality_snapshot: Mapping[str, float],
    memory_context: Mapping[str, float],
) -> Dict[str, Any]:
    """Read-copy-evaluate only. Never mutates supplied live structures or durable state."""
    live_before = deepcopy(dict(live_self_model))
    personality_before = deepcopy(dict(personality_snapshot))
    reflection = generate_reflection(
        current_self=live_before,
        desired_self=desired_self_model,
        personality=personality_before,
        memory_context=memory_context,
    )
    candidate = {
        "mode": "SHADOW_ONLY",
        "verification_status": "ARCHITECT_SEED_NOT_BUILDER_VERIFIED",
        "memory_id": memory.memory_id,
        "memory_fingerprint": memory.fingerprint(),
        "reflection": asdict(reflection),
        "reflection_fingerprint": reflection.fingerprint(),
        "proposed_changes": {
            "generated_motivation": reflection.motivation,
            "generated_goal": reflection.generated_goal,
            "behavioral_principle": reflection.behavioral_principle,
        },
        "live_write_performed": False,
    }
    candidate["shadow_hash"] = canonical_hash(candidate)
    if dict(live_self_model) != live_before or dict(personality_snapshot) != personality_before:
        raise RuntimeError("shadow evaluation mutated live input")
    return candidate
