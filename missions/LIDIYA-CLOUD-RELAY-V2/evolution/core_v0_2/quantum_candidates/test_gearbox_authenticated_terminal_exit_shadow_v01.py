import copy
import unittest

from gearbox_authenticated_terminal_exit_shadow_v01 import (
    TerminalExitGuardError, authenticated_terminal_exit, terminal_exit_boundaries,
)
from gearbox_authority_experience_signer_shadow_v01 import sign_for_regression
from gearbox_clock_epoch_recovery_shadow_v03 import ClockRecoveryProjection, REENTERED_STATE
from test_gearbox_clock_epoch_recovery_shadow_v03 import MISSION_BLOB, trust


def reentry():
    return ClockRecoveryProjection(
        state=REENTERED_STATE, epoch_id="epoch-current", secretary_level="UNKNOWN",
        pressure_inputs={"storage_pressure_ratio":0.0,"context_load_ratio":0.0,"tool_failure_ratio":0.0,"stale_pointer_ratio":0.0,"durable_progress_age_ratio":0.0},
        stale_pressure_carryover=False, prior_terminal_hold_carryover=False,
        routing_authority_allowed=False, formal_mutation_allowed=False,
        verified_experience_delta=0, operational_progress_delta=0, appraisal_delta=0,
        personality_delta=0, trauma_or_relief_delta=0, fresh_authority_required=False,
        reason="fresh authenticated reentry",
    )

def payload():
    return {
        "mission_state_blob_sha":MISSION_BLOB, "home_snapshot_id":"home-fresh-1",
        "goal_id":"goal-fresh-1", "goal_payload_hash":"a"*64,
        "authority_decision_id":"auth-2", "requested_control_state":"G1",
    }

def auth():
    t=trust()
    env={
        "schema_version":"1.0-shadow", "mission_id":"LCR-EVOLUTION-0005", "step_id":9,
        "authority_role":"LCR-A", "mission_state_blob_sha":MISSION_BLOB,
        "decision_id":"auth-2", "selected_state":"G1", "guard_status":"BRAKE",
        "return_condition":"fresh authority re-evaluation required", "checkpoint_required":True,
        "receiver_ack_required":True, "verification_gate":"NOT_PROMOTION_EVIDENCE",
        "formal_mutation_allowed":False,
    }
    s={"envelope":env,"signer_role":"LCR-A","key_epoch":t["authority_active_epoch"],"trust_snapshot_id":t["snapshot_id"]}
    s["signature"]=sign_for_regression(s,"LCR-A",s["key_epoch"])
    return s

class AuthenticatedTerminalExitShadowV01Tests(unittest.TestCase):
    def test_fresh_allowlisted_exit_resumes_shadow_routing(self):
        out=authenticated_terminal_exit(reentry=reentry(), exit_payload=payload(), signed_authority=auth(), signer_trust_snapshot=trust(), mission_state_blob_sha=MISSION_BLOB)
        self.assertTrue(out.routing_authority_allowed)
        self.assertEqual(out.secretary_level,"UNKNOWN")
        self.assertEqual(out.pressure_state,"NEUTRAL")
        self.assertEqual(out.verified_experience_delta,0)
        self.assertFalse(out.p_base_mutation)

    def test_terminal_exit_stale_state_reinjection_ab(self):
        clean=authenticated_terminal_exit(reentry=reentry(), exit_payload=payload(), signed_authority=auth(), signer_trust_snapshot=trust(), mission_state_blob_sha=MISSION_BLOB)
        stale_fields={
            "pressure_history":["YELLOW"]*100, "anti_thrash_age":9999, "terminal_hold_age":9999,
            "provider_retry_count":1000, "clock_retry_count":1000, "recovery_counter":77,
            "stale_goal_cache":{"goal":"old"}, "signer_familiarity":1.0,
        }
        for name,value in stale_fields.items():
            dirty=payload(); dirty[name]=value
            with self.assertRaises(TerminalExitGuardError):
                authenticated_terminal_exit(reentry=reentry(), exit_payload=dirty, signed_authority=auth(), signer_trust_snapshot=trust(), mission_state_blob_sha=MISSION_BLOB)
        clean2=authenticated_terminal_exit(reentry=reentry(), exit_payload=payload(), signed_authority=auth(), signer_trust_snapshot=trust(), mission_state_blob_sha=MISSION_BLOB)
        self.assertEqual(clean.cognitive_state(),clean2.cognitive_state())

    def test_unknown_field_fails_closed(self):
        p=payload(); p["mystery_history"]="x"
        with self.assertRaisesRegex(TerminalExitGuardError,"non-allowlisted"):
            authenticated_terminal_exit(reentry=reentry(), exit_payload=p, signed_authority=auth(), signer_trust_snapshot=trust(), mission_state_blob_sha=MISSION_BLOB)

    def test_fresh_authority_precedence(self):
        p=payload(); p["requested_control_state"]="G3"
        with self.assertRaisesRegex(TerminalExitGuardError,"authority precedence"):
            authenticated_terminal_exit(reentry=reentry(), exit_payload=p, signed_authority=auth(), signer_trust_snapshot=trust(), mission_state_blob_sha=MISSION_BLOB)

    def test_stale_reentry_cannot_exit(self):
        r=copy.deepcopy(reentry()); object.__setattr__(r,"stale_pressure_carryover",True)
        with self.assertRaisesRegex(TerminalExitGuardError,"stale recovery state"):
            authenticated_terminal_exit(reentry=r, exit_payload=payload(), signed_authority=auth(), signer_trust_snapshot=trust(), mission_state_blob_sha=MISSION_BLOB)

    def test_boundary_is_zero_learning(self):
        b=terminal_exit_boundaries()
        self.assertFalse(b["terminal_exit_counts_as_experience"])
        self.assertEqual(b["trauma_or_relief_delta"],0)
        self.assertEqual(b["personality_delta"],0)
        self.assertFalse(b["p_base_mutation_allowed"])
        self.assertFalse(b["formal_mutation_allowed"])

if __name__ == "__main__": unittest.main()
