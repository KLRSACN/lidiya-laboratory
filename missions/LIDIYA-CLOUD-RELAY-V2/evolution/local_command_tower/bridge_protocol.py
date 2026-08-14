from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

class EnvelopeError(ValueError):
    pass

def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def _body(envelope: Dict[str, Any]) -> Dict[str, Any]:
    return {k:v for k,v in envelope.items() if k != "envelope_sha256"}

def seal_envelope(envelope: Dict[str, Any]) -> Dict[str, Any]:
    out=dict(envelope)
    out["envelope_sha256"]=canonical_hash(_body(out))
    return out

def verify_envelope(envelope: Dict[str, Any], *, expected_mission: Optional[str]=None) -> bool:
    claimed=envelope.get("envelope_sha256")
    if not isinstance(claimed,str) or len(claimed)!=64:
        raise EnvelopeError("missing or invalid envelope_sha256")
    if canonical_hash(_body(envelope)) != claimed:
        raise EnvelopeError("envelope hash mismatch")
    if expected_mission is not None and envelope.get("mission_id") != expected_mission:
        raise EnvelopeError("mission mismatch")
    seq=envelope.get("sequence")
    if not isinstance(seq,int) or isinstance(seq,bool) or seq < 0:
        raise EnvelopeError("invalid sequence")
    return True

def make_task_envelope(*, mission_id: str, channel_id: str, sequence: int, task_id: str,
                       task_type: str, payload: Dict[str, Any], authority_snapshot_hash: str) -> Dict[str, Any]:
    return seal_envelope({
        "schema_version":"1.0","kind":"TASK","mission_id":mission_id,"channel_id":channel_id,
        "sequence":sequence,"task_id":task_id,"task_type":task_type,"payload":payload,
        "authority_snapshot_hash":authority_snapshot_hash
    })

def make_evidence_envelope(*, mission_id: str, channel_id: str, sequence: int, task_id: str,
                           result: str, evidence: Dict[str, Any], parent_task_sha256: str) -> Dict[str, Any]:
    return seal_envelope({
        "schema_version":"1.0","kind":"EVIDENCE","mission_id":mission_id,"channel_id":channel_id,
        "sequence":sequence,"task_id":task_id,"result":result,"evidence":evidence,
        "parent_task_sha256":parent_task_sha256
    })

@dataclass
class ReplayGuard:
    last_sequence: Dict[str,int] = field(default_factory=dict)
    seen_hashes: set[str] = field(default_factory=set)

    def accept(self, envelope: Dict[str,Any]) -> str:
        verify_envelope(envelope)
        h=envelope["envelope_sha256"]
        channel=str(envelope.get("channel_id",""))
        seq=envelope["sequence"]
        if h in self.seen_hashes:
            return "ALREADY_SEEN"
        last=self.last_sequence.get(channel,-1)
        if seq <= last:
            raise EnvelopeError("stale or replayed sequence")
        if seq != last + 1 and last >= 0:
            raise EnvelopeError("sequence jump")
        self.seen_hashes.add(h)
        self.last_sequence[channel]=seq
        return "ACCEPTED"
