from navigation_watchdog import *
S={"mission_id":"M","status":"BUILDING","step_id":2,"current_role":"LCR-B","pending_packet":"p","pending_packet_sha256":"h","lease":{"owner":"B"}}
def test_retry_preserves_authority():
    before=dict(S); d=decide(S,{"kind":"tool_failure","retry_count":0}); assert d.action=="RETRY_SAFE" and S==before
def test_rebuild_derived_only(): assert decide(S,{"kind":"stale_progress"}).action=="REBUILD_DERIVED_STATE"
def test_authority_conflict_fail_closed(): assert decide(S,{"authority_contradictions":["packet_hash"]}).action=="HUMAN_GATE"
def test_retry_exhaustion(): assert decide(S,{"kind":"tool_failure","retry_count":2},max_retries=2).action=="HUMAN_GATE"
def test_duplicate_nonexecuting():
    c=set(); e={"kind":"tool_failure","retry_count":0}; d=decide(S,e,consumed=c); mark_consumed(d,c); d2=decide(S,e,consumed=c); assert not d2.execution_authorized and d2.guard_status=="DEDUPED"
def test_protected_never_cleared(): assert decide(S,{"kind":"transient_artifact","flags":["protected"],"reproducible":True,"referenced":False}).action=="HUMAN_GATE"
def test_safe_transient_quarantine(): assert decide(S,{"kind":"transient_artifact","flags":[],"reproducible":True,"referenced":False}).action=="QUARANTINE_TRANSIENT"
