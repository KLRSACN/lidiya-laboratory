from dataclasses import dataclass, asdict
import hashlib, json

ACTIONS={"HEALTHY_CONTINUE","RETRY_SAFE","REBUILD_DERIVED_STATE","QUARANTINE_TRANSIENT","ROUTE_NEXT_ROLE","HUMAN_GATE"}
AUTH_FIELDS=("mission_id","status","step_id","current_role","pending_packet","pending_packet_sha256","lease")
PROTECTED={"protected","unique_human","secret_like","unreproducible","durable_referenced","identity","personality","governance"}

@dataclass(frozen=True)
class RecoveryDecision:
    action:str; recovery_id:str; reason:str; next_role_or_packet:str|None; retry_budget:int; guard_status:str; root_cause_lesson:str; execution_authorized:bool=False
    def to_dict(self): return asdict(self)

def recovery_id(state,event):
    payload={"state":{k:state.get(k) for k in AUTH_FIELDS},"event":event}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def decide(state,event,*,consumed=None,max_retries=2):
    consumed=consumed if consumed is not None else set(); rid=recovery_id(state,event)
    if rid in consumed: return RecoveryDecision("HUMAN_GATE",rid,"duplicate recovery is non-executing",None,0,"DEDUPED","duplicate recovery must not duplicate execution",False)
    contradictions=event.get("authority_contradictions",[])
    if contradictions: return RecoveryDecision("HUMAN_GATE",rid,"authority contradiction: "+",".join(sorted(contradictions)),None,0,"FAIL_CLOSED","never invent packet/hash/authorization/lease/role authority",False)
    kind=event.get("kind","healthy")
    if kind=="healthy": return RecoveryDecision("HEALTHY_CONTINUE",rid,"authoritative state healthy",state.get("current_role"),max_retries,"CLEAR","continue same mission",False)
    if kind=="tool_failure":
        used=int(event.get("retry_count",0))
        if used>=max_retries: return RecoveryDecision("HUMAN_GATE",rid,"retry budget exhausted",None,0,"ESCALATE","bounded retry prevents dead loop",False)
        return RecoveryDecision("RETRY_SAFE",rid,"temporary tool failure",state.get("pending_packet"),max_retries-used,"GUARDED","retry same durable action without resetting mission",True)
    if kind in {"stale_progress","missing_progress","stale_status"}: return RecoveryDecision("REBUILD_DERIVED_STATE",rid,"derived state is rebuildable",state.get("pending_packet"),max_retries,"AUTHORITATIVE_ONLY","rebuild only from durable authoritative state",True)
    if kind=="transient_artifact":
        flags={str(x).lower() for x in event.get("flags",[])}
        if flags & PROTECTED or not event.get("reproducible") or event.get("referenced"): return RecoveryDecision("HUMAN_GATE",rid,"artifact not safe to auto-clear",None,0,"FAIL_CLOSED","protected/ambiguous residue survives",False)
        return RecoveryDecision("QUARANTINE_TRANSIENT",rid,"reproducible unreferenced transient",state.get("current_role"),max_retries,"QUARANTINE","retain compact lesson/outcome only",True)
    if kind=="route_next": return RecoveryDecision("ROUTE_NEXT_ROLE",rid,"legal existing-role route",str(event.get("next_role")),max_retries,"GUARDED","route only within existing A/B/C",True)
    return RecoveryDecision("HUMAN_GATE",rid,"unknown recovery condition",None,0,"FAIL_CLOSED","unknown recovery must not mutate authority",False)

def mark_consumed(decision,consumed):
    if decision.execution_authorized: consumed.add(decision.recovery_id)
