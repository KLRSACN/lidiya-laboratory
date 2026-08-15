from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Iterable

_TOKEN=re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")
def normalize_goal_text(text: str) -> str:
    tokens=_TOKEN.findall(text.lower())
    if not tokens: raise ValueError("EMPTY_GOAL")
    return " ".join(tokens)
def semantic_key(text: str, lineage_hashes: Iterable[str]) -> str:
    normalized=normalize_goal_text(text)
    lineage=sorted(set(str(x) for x in lineage_hashes if x))
    if not lineage: raise ValueError("MISSING_GOAL_LINEAGE")
    return sha256((normalized+"|"+"|".join(lineage)).encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class GoalCandidate:
    goal_id: str
    text: str
    lineage_hashes: tuple[str,...]
    semantic_key: str
    authority_from_drive: int = 0
    external_action_allowed: bool = False

class SemanticGoalCanonicalizer:
    def __init__(self): self._seen:set[str]=set()
    def canonicalize(self, goal_id: str, text: str, lineage_hashes: Iterable[str]) -> GoalCandidate:
        line=tuple(sorted(set(str(x) for x in lineage_hashes if x)))
        return GoalCandidate(goal_id,normalize_goal_text(text),line,semantic_key(text,line))
    def admit_once(self, candidate: GoalCandidate) -> bool:
        if candidate.authority_from_drive != 0 or candidate.external_action_allowed:
            raise ValueError("GOAL_AUTHORITY_FORBIDDEN")
        if candidate.semantic_key in self._seen: return False
        self._seen.add(candidate.semantic_key); return True
