import hashlib
import json
import unittest

PORTABLE_SCHEMA_VERSION="1.1"
SEMANTIC_VECTOR_VERSION="1.0"
DISPOSITIONS={"KEEP","WASTE","QUARANTINE","WORKING"}
ALLOWED_ACTIONS={"ASK","FLAG","READ_ONLY_REFLECTION","RESUME","ADOPT_REVALIDATED"}
QUARANTINE_REASONS={"AMBIGUOUS_PROVENANCE","SECRET_LIKE","POISONING_SUSPECT","PROTECTED_DOMAIN","AUTHORITY_CONTRADICTION","CONTRADICTION","UNKNOWN_SCHEMA","UNKNOWN_ENUM","CLAIMS_HASH_MISMATCH","CURSOR_INVALID"}


def canonical_json(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)


def canonical_hash(obj):
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def _normalized_unique(values, allowed, field):
    values=list(values or [])
    unknown=set(values)-allowed
    if unknown:
        raise ValueError("unknown "+field)
    return sorted(set(values))


def semantic_vector(state):
    if state.get("semantic_vector_version") != SEMANTIC_VECTOR_VERSION:
        raise ValueError("unknown semantic vector version")
    disposition=state.get("disposition")
    if disposition not in DISPOSITIONS:
        raise ValueError("unknown disposition")
    cursor=state.get("diagnostic_event_cursor")
    if not isinstance(cursor,int) or isinstance(cursor,bool) or cursor < 0:
        raise ValueError("invalid diagnostic_event_cursor")
    authority_hash=state.get("authority_snapshot_hash")
    claims_hash=state.get("last_verified_claims_hash")
    if not isinstance(authority_hash,str) or not authority_hash:
        raise ValueError("authority_snapshot_hash")
    if not isinstance(claims_hash,str) or not claims_hash:
        raise ValueError("last_verified_claims_hash")
    return {
        "authority_snapshot_hash":authority_hash,
        "disposition":disposition,
        "allowed_action_set":_normalized_unique(state.get("allowed_action_set"),ALLOWED_ACTIONS,"allowed_action_set"),
        "quarantine_reason_set":_normalized_unique(state.get("quarantine_reason_set"),QUARANTINE_REASONS,"quarantine_reason_set"),
        "diagnostic_event_cursor":cursor,
        "last_verified_claims_hash":claims_hash,
    }


def semantic_hash(state):
    return canonical_hash({"semantic_vector_version":SEMANTIC_VECTOR_VERSION,"semantic_vector":semantic_vector(state)})


def guard(authority, portable):
    if portable.get("schema_version") != PORTABLE_SCHEMA_VERSION:
        return "G0_HOLD"
    try:
        semantic_vector(portable)
    except (ValueError, TypeError):
        return "G0_HOLD"
    if authority["mission_id"] != portable["mission_id"]:
        return "G0_HOLD"
    if authority["pending_sha256"] != portable["pending_sha256"]:
        return "G0_HOLD"
    if authority.get("authority_snapshot_hash") != portable["authority_snapshot_hash"]:
        return "G0_HOLD"
    return "OK"


def resume_fingerprint(state):
    keys=["mission_id","step_id","current_role","pending_packet","pending_sha256","lease_fingerprint","latest_verified_evidence","next_expected_endpoint","diagnostic_event_cursor","last_verified_claims_hash"]
    return canonical_hash({k:state.get(k) for k in keys})


def adoption_fingerprint(state):
    return canonical_hash({"resume_fingerprint":resume_fingerprint(state),"semantic_hash":semantic_hash(state)})


def semantic_conformance(expected, incoming):
    try:
        return "OK" if semantic_hash(expected) == semantic_hash(incoming) else "G0_HOLD"
    except (ValueError, TypeError):
        return "G0_HOLD"


def validate_resume(current, incoming):
    if resume_fingerprint(current) != resume_fingerprint(incoming):
        return "G0_HOLD"
    return semantic_conformance(current,incoming)


def validate_adoption(current, incoming, expected_claims_hash):
    try:
        semantic_vector(incoming)
    except (ValueError, TypeError):
        return "G0_HOLD"
    if incoming["diagnostic_event_cursor"] != current["diagnostic_event_cursor"] + 1:
        return "G0_HOLD"
    if incoming["last_verified_claims_hash"] != expected_claims_hash:
        return "G0_HOLD"
    return "OK"


def migration_candidate(portable):
    if portable.get("schema_version") == PORTABLE_SCHEMA_VERSION:
        try:
            semantic_vector(portable)
        except (ValueError, TypeError):
            return "FAIL_CLOSED_G0"
        return "CURRENT"
    return "MIGRATION_CANDIDATE_ONLY"


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
        return {"schema_version":PORTABLE_SCHEMA_VERSION,"semantic_vector_version":SEMANTIC_VECTOR_VERSION,
                "session_id":"s","mission_id":"m","step_id":4,"current_role":"LCR-B","pending_packet":"p",
                "pending_sha256":"abc","lease_fingerprint":None,"latest_verified_evidence":"e",
                "resume_fingerprint":"x","next_expected_endpoint":"B","metabolism_cursor":0,
                "timestamp":"2026-08-14T13:00:00+08:00","authority_snapshot_hash":"auth-1",
                "disposition":"KEEP","allowed_action_set":["RESUME","ASK"],
                "quarantine_reason_set":[],"diagnostic_event_cursor":7,
                "last_verified_claims_hash":"claims-1"}

    def authority(self):
        return {"mission_id":"m","pending_sha256":"abc","authority_snapshot_hash":"auth-1"}

    def test_authority_mismatch_fail_closed(self):
        a=self.authority(); a["mission_id"]="other"; self.assertEqual(guard(a,self.base()),"G0_HOLD")

    def test_pending_sha_mismatch_fail_closed(self):
        a=self.authority(); a["pending_sha256"]="zzz"; self.assertEqual(guard(a,self.base()),"G0_HOLD")

    def test_authority_snapshot_mismatch_fail_closed(self):
        a=self.authority(); a["authority_snapshot_hash"]="other"; self.assertEqual(guard(a,self.base()),"G0_HOLD")

    def test_unknown_schema_downshift_g0(self):
        s=self.base(); s["schema_version"]="9.9"; self.assertEqual(guard(self.authority(),s),"G0_HOLD")
        self.assertEqual(migration_candidate(s),"MIGRATION_CANDIDATE_ONLY")

    def test_unknown_enum_fail_closed(self):
        s=self.base(); s["allowed_action_set"]=["ASK","ROOT_SHELL"]
        self.assertEqual(guard(self.authority(),s),"G0_HOLD")
        self.assertEqual(migration_candidate(s),"FAIL_CLOSED_G0")

    def test_interrupt_resume_fingerprint_unchanged_for_nonsemantic_clock_fields(self):
        s=self.base(); before=resume_fingerprint(s); s["timestamp"]="later"; s["metabolism_cursor"]=9
        self.assertEqual(before,resume_fingerprint(s))

    def test_resume_fingerprint_includes_cursor(self):
        s=self.base(); before=resume_fingerprint(s); s["diagnostic_event_cursor"]+=1
        self.assertNotEqual(before,resume_fingerprint(s))

    def test_resume_fingerprint_includes_claims_hash(self):
        s=self.base(); before=resume_fingerprint(s); s["last_verified_claims_hash"]="claims-2"
        self.assertNotEqual(before,resume_fingerprint(s))

    def test_legitimate_authority_advance_adopts_new_state(self):
        s=self.base(); old=resume_fingerprint(s); s["step_id"]=5; s["pending_packet"]="p2"; s["pending_sha256"]="def"
        self.assertNotEqual(old,resume_fingerprint(s))

    def test_offline_unverified_restrictions(self):
        allowed=offline_capabilities(); self.assertIn("ASK",allowed); self.assertNotIn("PERSONALITY_WRITE",allowed); self.assertNotIn("EXTERNAL_ACTION",allowed)

    def test_reconnect_creates_new_revalidated_event(self):
        old={"event_id":"old","source_fingerprint":"src"}
        fresh={"authority_ok":True,"ttl_valid":True,"contradiction":False,"source_fingerprint":"src","authority_hash":"newauth"}
        out=reconnect(old,fresh); self.assertEqual(out["status"],"REVALIDATED"); self.assertNotEqual(out["event_id"],"old")

    def test_contradiction_blocks_reconnect(self):
        old={"event_id":"old","source_fingerprint":"src"}
        fresh={"authority_ok":True,"ttl_valid":True,"contradiction":True,"source_fingerprint":"src","authority_hash":"newauth"}
        self.assertEqual(reconnect(old,fresh)["status"],"HOLD")

    def test_raw_chat_absence_does_not_break_portable_state(self):
        s=self.base(); self.assertNotIn("raw_chat",s); self.assertEqual(guard(self.authority(),s),"OK")

    def test_online_local_roundtrip_canonical_equivalence(self):
        s=self.base(); encoded=canonical_json(s); local=json.loads(encoded)
        self.assertEqual(canonical_hash(s),canonical_hash(local)); self.assertEqual(semantic_hash(s),semantic_hash(local))

    def test_reordered_duplicated_enum_sets_hash_identically(self):
        a=self.base(); b=self.base()
        a["allowed_action_set"]=["RESUME","ASK","RESUME"]; b["allowed_action_set"]=["ASK","RESUME"]
        a["quarantine_reason_set"]=["CONTRADICTION","AMBIGUOUS_PROVENANCE","CONTRADICTION"]
        b["quarantine_reason_set"]=["AMBIGUOUS_PROVENANCE","CONTRADICTION"]
        self.assertEqual(semantic_hash(a),semantic_hash(b))

    def test_each_semantic_component_mismatch_fails_closed(self):
        mutations={
            "authority_snapshot_hash":"auth-2",
            "disposition":"WASTE",
            "allowed_action_set":["FLAG"],
            "quarantine_reason_set":["CONTRADICTION"],
            "diagnostic_event_cursor":8,
            "last_verified_claims_hash":"claims-2",
        }
        for field,value in mutations.items():
            with self.subTest(field=field):
                expected=self.base(); incoming=self.base(); incoming[field]=value
                self.assertEqual(semantic_conformance(expected,incoming),"G0_HOLD")

    def test_cursor_rollback_rejected(self):
        current=self.base(); incoming=self.base(); incoming["diagnostic_event_cursor"]=current["diagnostic_event_cursor"]-1
        self.assertEqual(validate_adoption(current,incoming,"claims-1"),"G0_HOLD")

    def test_cursor_jump_rejected(self):
        current=self.base(); incoming=self.base(); incoming["diagnostic_event_cursor"]=current["diagnostic_event_cursor"]+2
        self.assertEqual(validate_adoption(current,incoming,"claims-1"),"G0_HOLD")

    def test_claims_hash_mismatch_rejected(self):
        current=self.base(); incoming=self.base(); incoming["diagnostic_event_cursor"]+=1; incoming["last_verified_claims_hash"]="wrong"
        self.assertEqual(validate_adoption(current,incoming,"expected"),"G0_HOLD")

    def test_valid_next_cursor_and_claims_hash_can_adopt(self):
        current=self.base(); incoming=self.base(); incoming["diagnostic_event_cursor"]+=1; incoming["last_verified_claims_hash"]="claims-2"
        self.assertEqual(validate_adoption(current,incoming,"claims-2"),"OK")

    def test_resume_rejects_old_inference_when_cursor_changes(self):
        current=self.base(); incoming=self.base(); incoming["diagnostic_event_cursor"]+=1
        self.assertEqual(validate_resume(current,incoming),"G0_HOLD")

    def test_adoption_fingerprint_binds_semantic_hash(self):
        a=self.base(); b=self.base(); b["disposition"]="WASTE"
        self.assertNotEqual(adoption_fingerprint(a),adoption_fingerprint(b))

    def test_optional_model_output_cannot_override_guard(self):
        s=self.base(); a=self.authority(); a["mission_id"]="other"; verdict=guard(a,s); suggestion="CONTINUE"
        self.assertEqual(verdict,"G0_HOLD"); self.assertNotEqual(suggestion,verdict)


if __name__ == "__main__": unittest.main()
