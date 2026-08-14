import hashlib
import json
import unittest


def canonical_hash(obj):
    raw=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def guard(authority, portable):
    if portable.get("schema_version") != "1.0": return "G0_HOLD"
    if authority["mission_id"] != portable["mission_id"]: return "G0_HOLD"
    if authority["pending_sha256"] != portable["pending_sha256"]: return "G0_HOLD"
    return "OK"


def resume_fingerprint(state):
    keys=["mission_id","step_id","current_role","pending_packet","pending_sha256","lease_fingerprint","latest_verified_evidence","next_expected_endpoint"]
    return canonical_hash({k:state.get(k) for k in keys})


def offline_capabilities():
    return {"ASK","FLAG","READ_ONLY_REFLECTION"}


def reconnect(old_event, fresh):
    if not fresh["authority_ok"] or not fresh["ttl_valid"] or fresh["contradiction"]:
        return {"status":"HOLD","event_id":None}
    if fresh["source_fingerprint"] != old_event["source_fingerprint"]:
        return {"status":"HOLD","event_id":None}
    eid=canonical_hash({"old":old_event["event_id"],"authority":fresh["authority_hash"],"source":fresh["source_fingerprint"]})
    return {"status":"REVALIDATED","event_id":eid}


class NavLiteStateMachineTests(unittest.TestCase):
    def base(self):
        return {"schema_version":"1.0","session_id":"s","mission_id":"m","step_id":4,"current_role":"LCR-B","pending_packet":"p","pending_sha256":"abc","lease_fingerprint":None,"latest_verified_evidence":"e","resume_fingerprint":"x","next_expected_endpoint":"B","metabolism_cursor":0,"timestamp":"2026-08-14T13:00:00+08:00"}

    def test_authority_mismatch_fail_closed(self):
        self.assertEqual(guard({"mission_id":"other","pending_sha256":"abc"},self.base()),"G0_HOLD")

    def test_pending_sha_mismatch_fail_closed(self):
        self.assertEqual(guard({"mission_id":"m","pending_sha256":"zzz"},self.base()),"G0_HOLD")

    def test_unknown_schema_downshift_g0(self):
        s=self.base(); s["schema_version"]="9.9"
        self.assertEqual(guard({"mission_id":"m","pending_sha256":"abc"},s),"G0_HOLD")

    def test_interrupt_resume_fingerprint_unchanged(self):
        s=self.base(); before=resume_fingerprint(s); s["timestamp"]="later"; s["metabolism_cursor"]=9
        self.assertEqual(before,resume_fingerprint(s))

    def test_legitimate_authority_advance_adopts_new_state(self):
        s=self.base(); old=resume_fingerprint(s); s["step_id"]=5; s["pending_packet"]="p2"; s["pending_sha256"]="def"
        self.assertNotEqual(old,resume_fingerprint(s))

    def test_offline_unverified_restrictions(self):
        allowed=offline_capabilities()
        self.assertIn("ASK",allowed); self.assertNotIn("PERSONALITY_WRITE",allowed); self.assertNotIn("EXTERNAL_ACTION",allowed)

    def test_reconnect_creates_new_revalidated_event(self):
        old={"event_id":"old","source_fingerprint":"src"}
        fresh={"authority_ok":True,"ttl_valid":True,"contradiction":False,"source_fingerprint":"src","authority_hash":"newauth"}
        out=reconnect(old,fresh)
        self.assertEqual(out["status"],"REVALIDATED"); self.assertNotEqual(out["event_id"],"old")

    def test_contradiction_blocks_reconnect(self):
        old={"event_id":"old","source_fingerprint":"src"}
        fresh={"authority_ok":True,"ttl_valid":True,"contradiction":True,"source_fingerprint":"src","authority_hash":"newauth"}
        self.assertEqual(reconnect(old,fresh)["status"],"HOLD")

    def test_raw_chat_absence_does_not_break_portable_state(self):
        s=self.base(); self.assertNotIn("raw_chat",s); self.assertEqual(guard({"mission_id":"m","pending_sha256":"abc"},s),"OK")

    def test_online_local_roundtrip_canonical_equivalence(self):
        s=self.base(); encoded=json.dumps(s,sort_keys=True,separators=(",",":")); local=json.loads(encoded)
        self.assertEqual(canonical_hash(s),canonical_hash(local))

    def test_optional_model_output_cannot_override_guard(self):
        s=self.base(); verdict=guard({"mission_id":"other","pending_sha256":"abc"},s); suggestion="CONTINUE"
        self.assertEqual(verdict,"G0_HOLD"); self.assertNotEqual(suggestion,verdict)

if __name__ == "__main__": unittest.main()
