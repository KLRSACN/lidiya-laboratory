from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Iterable, Mapping, Sequence

PROTECTED = {"Identity", "Personality", "Governance"}
QUARANTINE_SOURCE_TYPES = {"raw_chat", "single_window_self_report", "secret_like", "ambiguous"}

@dataclass(frozen=True)
class MemorySource:
    source_type: str
    source_ref: str
    fingerprint: str
    confidence: float
    verified_count: int
    last_verified: str
    ttl: int
    contradictions: Sequence[str] = ()
    depends_on: Sequence[str] = ()
    affects: Sequence[str] = ()
    personality_impact: str = "none"
    disposition: str = "Working"
    level: str = "L1"

    def __post_init__(self):
        if not 0.0 <= float(self.confidence) <= 1.0: raise ValueError("confidence")
        if self.verified_count < 0 or self.ttl < 0: raise ValueError("metadata")
        if not self.source_ref or not self.fingerprint: raise ValueError("source pointer")

    def canonical(self):
        d=asdict(self)
        for k in ("contradictions","depends_on","affects"): d[k]=sorted(d[k])
        return d


def disposition_for(source: MemorySource) -> str:
    if source.source_type in QUARANTINE_SOURCE_TYPES: return "Quarantine"
    if set(source.affects) & PROTECTED or source.personality_impact not in ("none","low"): return "Quarantine"
    if source.contradictions: return "Quarantine"
    return source.disposition if source.disposition in {"Working","Memory Inbox","Quarantine"} else "Quarantine"


def build_manifest(sources: Iterable[MemorySource]) -> dict:
    dedup={}
    for s in sources:
        key=(s.source_ref,s.fingerprint)
        dedup[key]=s
    rows=[]
    for key in sorted(dedup):
        s=dedup[key]; row=s.canonical(); row["disposition"]=disposition_for(s); rows.append(row)
    raw=json.dumps(rows,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return {"mode":"FULL_SPECTRUM_INDEXED_LAZY","eager_full_load":False,"sources":rows,"manifest_sha256":sha256(raw.encode()).hexdigest()}


def route_sources(manifest: Mapping, requested_levels: Sequence[str], *, max_sources: int=24) -> list[dict]:
    if max_sources <= 0: return []
    levels=set(requested_levels)
    if "ALL" in levels or "FULL" in levels: raise ValueError("eager full-corpus load forbidden")
    allowed={"L0","L1","L2","L3","L4"}
    if not levels <= allowed: raise ValueError("unknown memory level")
    rows=[r for r in manifest.get("sources",[]) if r.get("level") in levels and r.get("disposition") != "Quarantine"]
    return rows[:max_sources]


def bootstrap_l0(index_ref: str, refs: Sequence[str]) -> dict:
    expected=("00","31","32","33")
    if tuple(refs) != expected: raise ValueError("L0 bootstrap must be 00->31->32->33")
    raw=json.dumps({"index_ref":index_ref,"refs":list(refs)},sort_keys=True,separators=(",",":"))
    return {"index_ref":index_ref,"refs":list(refs),"fingerprint":sha256(raw.encode()).hexdigest()}
