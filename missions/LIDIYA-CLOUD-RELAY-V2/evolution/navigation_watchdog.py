from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib, json

ACTIONS={"HEALTHY_CONTINUE","RETRY_SAFE","REBUILD_DERIVED_STATE","QUARANTINE_TRANSIENT","ROUTE_NEXT_ROLE","HUMAN_GATE"}
LEGAL_ROLES={"LCR-A","LCR-B","LCR-C"}
ACTIVE_PENDING_STATES={"READY_FOR_BUILDER","BUILDING","READY_FOR_VERIFY","VERIFYING","STEP_DONE"}
AUTH_FIELDS=("mission_id","status","step_id","current_role","next_role","pending_packet","pending_packet_sha256","authorization_ref","lease")
PROTECTED={"protected","unique_human","secret_like","unreproducible","durable_referenced","identity","personality","governance"}

@dataclass(frozen=True)
class RecoveryDecision:
    action:str; recovery_id:str; reason:str; next_role_or_packet:str|None; retry_budget:int; guard_status:str; root_cause_lesson:str; execution_authorized:bool=False
    def to_dict(self): return asdict(self)

def recovery_id(state,event):
    payload={"state":{k:state.get(k) for k in AUTH_FIELDS},"event":event}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def _gate(rid,reason,lesson="never invent packet/hash/authorization/lease/role authority"):
    return RecoveryDecision("HUMAN_GATE",rid,reason,None,0,"FAIL_CLOSED",lesson,False)

def _parse_time(value):
    if not isinstance(value,str) or not value: raise ValueError("missing time")
    return datetime.fromisoformat(value.replace("Z","+00:00"))

def _authority_error(state,event):
    role=state.get("current_role")
    next_role=state.get("next_role")
    if role not in LEGAL_ROLES: return "current_role outside A/B/C"
    if next_role is not None and next_role not in LEGAL_ROLES: return "next_role outside A/B/C"
    if event.get("expected_current_role") is not None and event["expected_current_role"]!=role: return "current-role mismatch"

    if state.get("status") in ACTIVE_PENDING_STATES:
        if not state.get("pending_packet"): return "missing pending packet"
        if not state.get("pending_packet_sha256"): return "missing pending packet hash"

    checks=(("expected_packet","pending_packet"),("expected_hash","pending_packet_sha256"),("expected_authorization_ref","authorization_ref"))
    for supplied,durable in checks:
        if event.get(supplied) is not None and event[supplied]!=state.get(durable): return f"{supplied} mismatch"

    lease=state.get("lease")
    if lease is not None:
        if not isinstance(lease,dict): return "malformed lease"
        if not all(lease.get(k) for k in ("owner","role","expires_at")): return "malformed lease"
        if lease.get("role") not in LEGAL_ROLES or lease.get("role")!=role: return "lease role mismatch"
        try: _parse_time(lease["expires_at"])
        except (TypeError,ValueError): return "malformed lease expiry"
        expected_owner=event.get("expected_lease_owner")
        if expected_owner is not None and expected_owner!=lease.get("owner"): return "conflicting lease"
    elif event.get("expected_lease_owner") is not None:
        return "missing expected lease"
    return None

def decide(state,event,*,consumed=None,max_retries=2):
    consumed=consumed if consumed is not None else set(); rid=recovery_id(state,event)
    if rid in consumed: return RecoveryDecision("HUMAN_GATE",rid,"duplicate recovery is non-executing",None,0,"DEDUPED","duplicate recovery must not duplicate execution",False)

    err=_authority_error(state,event)
    if err: return _gate(rid,err)
    contradictions=event.get("authority_contradictions",[])
    if contradictions: return _gate(rid,"authority contradiction: "+",".join(sorted(contradictions)))

    kind=event.get("kind","healthy")
    if kind=="healthy": return RecoveryDecision("HEALTHY_CONTINUE",rid,"authoritative state healthy",state.get("current_role"),max_retries,"CLEAR","continue same mission",False)
    if kind=="tool_failure":
        used=int(event.get("retry_count",0))
        if used>=max_retries: return _gate(rid,"retry budget exhausted","bounded retry prevents dead loop")
        return RecoveryDecision("RETRY_SAFE",rid,"temporary tool failure",state.get("pending_packet"),max_retries-used,"GUARDED","retry same durable action without resetting mission",True)
    if kind in {"stale_progress","missing_progress","stale_status","stale_roster"}:
        return RecoveryDecision("REBUILD_DERIVED_STATE",rid,"derived state is rebuildable",state.get("pending_packet"),max_retries,"AUTHORITATIVE_ONLY","rebuild derived state only; authoritative mission fields remain unchanged",True)
    if kind=="transient_artifact":
        flags={str(x).lower() for x in event.get("flags",[])}
        if flags & PROTECTED or not event.get("reproducible") or event.get("referenced"): return _gate(rid,"artifact not safe to auto-clear","protected/ambiguous residue survives")
        return RecoveryDecision("QUARANTINE_TRANSIENT",rid,"reproducible unreferenced transient",state.get("current_role"),max_retries,"QUARANTINE","retain compact lesson/outcome only",True)
    if kind=="route_next":
        requested=event.get("next_role")
        route_packet=event.get("route_packet")
        route_hash=event.get("route_hash")
        if requested not in LEGAL_ROLES: return _gate(rid,"illegal route role")
        if requested!=state.get("next_role"): return _gate(rid,"route role is not authoritative next_role")
        if not route_packet or route_packet!=state.get("pending_packet"): return _gate(rid,"route packet is not authoritative pending packet")
        if not route_hash or route_hash!=state.get("pending_packet_sha256"): return _gate(rid,"route hash is not authoritative pending hash")
        return RecoveryDecision("ROUTE_NEXT_ROLE",rid,"exact legal durable route",requested,max_retries,"GUARDED","route only after exact role/packet/hash proof",True)
    return _gate(rid,"unknown recovery condition","unknown recovery must not mutate authority")

def mark_consumed(decision,consumed):
    if decision.execution_authorized: consumed.add(decision.recovery_id)
