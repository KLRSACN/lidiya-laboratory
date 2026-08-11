"""Branch-local Golden Triangle orchestration candidate for LCR-METABOLISM-0003."""
from __future__ import annotations
import hashlib, json

SLOTS=("LCR-A","LCR-B","LCR-C")
BACKUPS=("RECOVERY_BASELINE","WORKING_EXCHANGE")

class GuardError(ValueError): pass

def canonical(obj): return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def digest(obj): return hashlib.sha256(canonical(obj)).hexdigest()

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

def consume_and_dispatch(state,packet,target):
    """Resume-safe transition. packet_sha is the durable identity."""
    psha=packet["packet_sha256"]
    if psha in state.get("consumed_packet_sha256",[]): raise GuardError("replay rejected")
    if state.get("pending_packet_sha256")!=psha: raise GuardError("pending hash mismatch")
    if packet.get("target")!=state.get("current_role"): raise GuardError("role mismatch")
    if target not in SLOTS: raise GuardError("slot 4 rejected")
    out=json.loads(json.dumps(state)); out.setdefault("consumed_packet_sha256",[]).append(psha); out["last_packet_sha256"]=psha
    out["current_role"]=target; out["next_role"]=target; out["lease"]=None
    return out

def make_handoff(source,target,parent_sha,step):
    if source not in SLOTS or target not in SLOTS: raise GuardError("invalid slot")
    body={"mission_id":"LCR-METABOLISM-0003","step_id":step,"source":source,"target":target,"parent_packet_sha256":parent_sha,"status":"READY"}
    body["packet_sha256"]=digest(body); return body
