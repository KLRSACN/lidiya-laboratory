"""Branch-local Golden Triangle orchestration candidate for LCR-METABOLISM-0003."""
from __future__ import annotations
import hashlib, json

SLOTS=("LCR-A","LCR-B","LCR-C")
BACKUPS=("RECOVERY_BASELINE","WORKING_EXCHANGE")

class GuardError(ValueError): pass

def canonical(obj): return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def digest(obj): return hashlib.sha256(canonical(obj)).hexdigest()
def packet_digest(packet): return digest({k:v for k,v in packet.items() if k!="packet_sha256"})

def validate_slots(slots):
    if tuple(sorted(slots)) != tuple(sorted(SLOTS)) or len(slots)!=3: raise GuardError("exactly A/B/C required")
    return True

def validate_backups(groups):
    if tuple(groups)!=BACKUPS: raise GuardError("only RECOVERY_BASELINE + WORKING_EXCHANGE allowed")
    return True

def register_or_takeover(registry,slot,worker,handoff=None):
    validate_slots(registry.keys())
    if slot not in SLOTS: raise GuardError("slot 4 rejected")
    current=registry[slot]
    if current==worker: return dict(registry)
    if not handoff or handoff.get("slot")!=slot or handoff.get("from")!=current or handoff.get("to")!=worker or not handoff.get("authorized"):
        raise GuardError("valid durable same-slot handoff required")
    out=dict(registry); out[slot]=worker; return out

def consume_and_dispatch(state,packet,target,next_packet_path=None,next_packet=None):
    """Consume an inbound packet only after content-derived integrity validation.

    When dispatching onward, exact next packet path/hash are persisted so a fresh
    worker can recover the next handoff from durable state alone.
    """
    claimed=packet.get("packet_sha256")
    actual=packet_digest(packet)
    if not claimed or claimed!=actual: raise GuardError("packet content hash mismatch")
    if actual in state.get("consumed_packet_sha256",[]): raise GuardError("replay rejected")
    if state.get("pending_packet_sha256")!=actual: raise GuardError("pending hash mismatch")
    if packet.get("target")!=state.get("current_role"): raise GuardError("role mismatch")
    if target not in SLOTS: raise GuardError("slot 4 rejected")
    out=json.loads(json.dumps(state)); out.setdefault("consumed_packet_sha256",[]).append(actual); out["last_packet_sha256"]=actual
    out["current_role"]=target; out["next_role"]=target; out["lease"]=None
    if next_packet is not None:
        if not next_packet_path: raise GuardError("next packet path required")
        next_claimed=next_packet.get("packet_sha256")
        next_actual=packet_digest(next_packet)
        if not next_claimed or next_claimed!=next_actual: raise GuardError("next packet content hash mismatch")
        if next_packet.get("target")!=target: raise GuardError("next packet target mismatch")
        out["pending_packet"]=next_packet_path
        out["pending_packet_sha256"]=next_actual
    elif next_packet_path is not None:
        raise GuardError("next packet body required")
    else:
        out["pending_packet"]=None; out["pending_packet_sha256"]=None
    return out

def recover_next_handoff(state):
    """Return the exact durable next handoff identity after worker restart."""
    path=state.get("pending_packet"); sha=state.get("pending_packet_sha256")
    if not path or not sha or state.get("current_role") not in SLOTS: raise GuardError("durable next handoff incomplete")
    return {"target":state["current_role"],"pending_packet":path,"pending_packet_sha256":sha}

def make_handoff(source,target,parent_sha,step):
    if source not in SLOTS or target not in SLOTS: raise GuardError("invalid slot")
    body={"mission_id":"LCR-METABOLISM-0003","step_id":step,"source":source,"target":target,"parent_packet_sha256":parent_sha,"status":"READY"}
    body["packet_sha256"]=packet_digest(body); return body
