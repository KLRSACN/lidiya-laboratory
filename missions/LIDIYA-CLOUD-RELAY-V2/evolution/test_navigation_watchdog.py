from navigation_watchdog import *
from unittest.mock import patch
from datetime import datetime

NOW="2026-08-12T18:20:00+08:00"
ROSTER={"current_role":"LCR-B","registry":{"LCR-A":{"worker_id":"A"},"LCR-B":{"worker_id":"ONLINE-LIDIYA-SECONDARY-INTEGRATOR"},"LCR-C":{"worker_id":"C"}}}
_raw_decide=decide
def decide(state,event,**kw):
    kw.setdefault("roster",ROSTER)
    with patch("navigation_watchdog._trusted_now",return_value=datetime.fromisoformat(NOW)):
        return _raw_decide(state,event,**kw)

LEASE={"owner":"ONLINE-LIDIYA-SECONDARY-INTEGRATOR","role":"LCR-B","expires_at":"2026-08-12T18:46:00+08:00"}
S={"mission_id":"M","status":"BUILDING","step_id":2,"current_role":"LCR-B","next_role":"LCR-B","pending_packet":"p","pending_packet_sha256":"h","authorization_ref":"auth","lease":LEASE}

def ev(kind="healthy",**kw):
    base={"kind":kind,"expected_current_role":"LCR-B","expected_packet":"p","expected_hash":"h","expected_authorization_ref":"auth","expected_lease_owner":"ONLINE-LIDIYA-SECONDARY-INTEGRATOR"}
    base.update(kw); return base

def test_retry_preserves_authority():
    before=json.loads(json.dumps(S)); d=decide(S,ev("tool_failure",retry_count=0)); assert d.action=="RETRY_SAFE" and S==before
def test_rebuild_derived_only(): assert decide(S,ev("stale_progress")).action=="REBUILD_DERIVED_STATE"
def test_stale_roster_rebuild_does_not_override_mission():
    before=json.loads(json.dumps(S)); d=decide(S,ev("stale_roster")); assert d.action=="REBUILD_DERIVED_STATE" and S==before and d.next_role_or_packet=="p"
def test_authority_conflict_fail_closed(): assert decide(S,ev(authority_contradictions=["packet_hash"])).action=="HUMAN_GATE"
def test_retry_exhaustion(): assert decide(S,ev("tool_failure",retry_count=2),max_retries=2).action=="HUMAN_GATE"
def test_duplicate_nonexecuting():
    c=set(); e=ev("tool_failure",retry_count=0); d=decide(S,e,consumed=c); mark_consumed(d,c); d2=decide(S,e,consumed=c); assert not d2.execution_authorized and d2.guard_status=="DEDUPED"
def test_stale_recovery_nonexecuting():
    c=set(); e=ev("stale_progress"); d=decide(S,e,consumed=c); mark_consumed(d,c); d2=decide(S,e,consumed=c); assert d2.guard_status=="DEDUPED" and not d2.execution_authorized
def test_protected_never_cleared(): assert decide(S,ev("transient_artifact",flags=["protected"],reproducible=True,referenced=False)).action=="HUMAN_GATE"
def test_safe_transient_quarantine(): assert decide(S,ev("transient_artifact",flags=[],reproducible=True,referenced=False)).action=="QUARANTINE_TRANSIENT"
def test_missing_pending_packet_fail_closed():
    s=dict(S); s["pending_packet"]=None; assert decide(s,{"kind":"tool_failure"}).action=="HUMAN_GATE"
def test_missing_pending_hash_fail_closed():
    s=dict(S); s["pending_packet_sha256"]=None; assert decide(s,{"kind":"tool_failure"}).action=="HUMAN_GATE"
def test_wrong_expected_hash_fail_closed(): assert decide(S,ev(expected_hash="WRONG")).action=="HUMAN_GATE"
def test_wrong_expected_packet_fail_closed(): assert decide(S,ev(expected_packet="WRONG")).action=="HUMAN_GATE"
def test_wrong_authorization_fail_closed(): assert decide(S,ev(expected_authorization_ref="WRONG")).action=="HUMAN_GATE"
def test_role_outside_abc_fail_closed():
    s=dict(S); s["current_role"]="LCR-D"; assert decide(s,{"kind":"healthy"}).action=="HUMAN_GATE"
def test_current_role_mismatch_fail_closed(): assert decide(S,ev(expected_current_role="LCR-C")).action=="HUMAN_GATE"
def test_malformed_lease_fail_closed():
    s=dict(S); s["lease"]={"owner":"x"}; assert decide(s,{"kind":"healthy"}).action=="HUMAN_GATE"
def test_conflicting_lease_fail_closed(): assert decide(S,ev(expected_lease_owner="OTHER")).action=="HUMAN_GATE"
def test_route_lcr_d_nonexecuting(): assert not decide(S,ev("route_next",next_role="LCR-D",route_packet="p",route_hash="h")).execution_authorized
def test_route_wrong_role_nonexecuting():
    s=dict(S); s["next_role"]="LCR-C"; assert not decide(s,{"kind":"route_next","next_role":"LCR-B","route_packet":"p","route_hash":"h"}).execution_authorized
def test_route_wrong_packet_nonexecuting(): assert not decide(S,ev("route_next",next_role="LCR-B",route_packet="wrong",route_hash="h")).execution_authorized
def test_route_wrong_hash_nonexecuting(): assert not decide(S,ev("route_next",next_role="LCR-B",route_packet="p",route_hash="wrong")).execution_authorized
def test_route_exact_authority_executes_once():
    c=set(); e=ev("route_next",next_role="LCR-B",route_packet="p",route_hash="h"); d=decide(S,e,consumed=c); assert d.action=="ROUTE_NEXT_ROLE" and d.execution_authorized; mark_consumed(d,c); assert not decide(S,e,consumed=c).execution_authorized

def test_expired_lease_rejected():
    s=dict(S); s["lease"]={**LEASE,"expires_at":"2026-08-12T18:19:59+08:00"}; assert decide(s,{"kind":"healthy"}).reason=="expired lease"
def test_naive_expiry_rejected():
    s=dict(S); s["lease"]={**LEASE,"expires_at":"2026-08-12T18:46:00"}; assert decide(s,{"kind":"healthy"}).reason=="malformed lease expiry"
def test_owner_must_match_roster_without_hint():
    s=dict(S); s["lease"]={**LEASE,"owner":"OTHER"}; assert decide(s,{"kind":"healthy"}).reason=="foreign lease owner"
def test_missing_roster_rejected():
    with patch("navigation_watchdog._trusted_now",return_value=datetime.fromisoformat(NOW)):
        assert _raw_decide(S,{"kind":"healthy"}).reason=="cannot prove lease owner"
def test_roster_role_mismatch_rejected():
    r={**ROSTER,"current_role":"LCR-C"}
    with patch("navigation_watchdog._trusted_now",return_value=datetime.fromisoformat(NOW)):
        assert _raw_decide(S,{"kind":"healthy"},roster=r).reason=="cannot prove lease owner"
def test_disabled_continuation_is_rebuildable_not_done():
    before=json.loads(json.dumps(S)); d=decide(S,ev("continuation_disabled")); assert d.action=="REBUILD_DERIVED_STATE" and d.execution_authorized and S==before

def test_caller_stale_now_cannot_override_trusted_clock():
    s=dict(S); s["lease"]={**LEASE,"expires_at":"2026-08-12T18:19:59+08:00"}
    with patch("navigation_watchdog._trusted_now",return_value=datetime.fromisoformat(NOW)):
        d=_raw_decide(s,{"kind":"healthy"},roster=ROSTER,now="2000-01-01T00:00:00+00:00")
    assert d.reason=="expired lease" and not d.execution_authorized

def test_caller_future_now_cannot_expire_valid_lease():
    with patch("navigation_watchdog._trusted_now",return_value=datetime.fromisoformat(NOW)):
        d=_raw_decide(S,{"kind":"healthy"},roster=ROSTER,now="2999-01-01T00:00:00+00:00")
    assert d.action=="HEALTHY_CONTINUE"
