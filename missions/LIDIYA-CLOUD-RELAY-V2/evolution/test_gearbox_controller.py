import unittest

from gearbox_controller import GearboxGuardError, capture_owner_input_without_rpm_drop, compact_torque_state, overlap_shift, select_gear, validate_formal_roster

BASE = dict(risk="LOW", uncertainty=0.1, evidence_quality=0.9, task_complexity=0.5, reversibility=True, contradiction=False, hard_safety_conflict=False, rollback_required=False, standby=False, storage_pressure_ratio=0.1, proposed_autonomy=6)

def ACTIVE_STATE():
    return {
        "mission_id":"LCR-EVOLUTION-0005","status":"READY_FOR_BUILDER","step_id":1,"current_role":"LCR-B",
        "pending_packet":"packets/EVOLUTION-0005-A-TO-B-STEP-001.json","pending_packet_sha256":"a"*64,"lease":None,
        "route":{"current_goal":"build gearbox"},"latest_verified_evidence":"evidence/previous.json","rollback_anchor":"nav-relay-mvp-0001",
        "blocker":None,"priority":"NORMAL","return_condition":"C PASS then benchmark models","raw_chat":"must not transfer",
    }

class GearboxTests(unittest.TestCase):
    def test_same_input_is_deterministic(self): self.assertEqual(select_gear(**BASE), select_gear(**BASE))
    def test_expected_structured_fields_present(self): self.assertEqual(set(select_gear(**BASE).to_dict()), {"selected_gear","specialist","reason","guard_status","return_condition","expected_cost_class"})
    def test_standby_and_reverse(self):
        self.assertEqual(select_gear(**{**BASE, "standby":True}).selected_gear, "N")
        self.assertEqual(select_gear(**{**BASE, "rollback_required":True}).selected_gear, "R")
    def test_high_risk_cannot_upshift_even_if_forged_high_confidence(self):
        d=select_gear(**{**BASE,"risk":"CRITICAL","uncertainty":0.0,"evidence_quality":1.0,"task_complexity":1.0,"proposed_autonomy":6})
        self.assertEqual(d.selected_gear,"G1"); self.assertIn(d.guard_status,{"BRAKE","HUMAN_GATE"})
    def test_hard_safety_conflict_human_gate(self): self.assertEqual((lambda d:(d.selected_gear,d.guard_status))(select_gear(**{**BASE,"hard_safety_conflict":True})),("G1","HUMAN_GATE"))
    def test_contradiction_downshifts(self): self.assertEqual(select_gear(**{**BASE,"contradiction":True}).selected_gear,"G1")
    def test_weak_evidence_downshifts(self): self.assertEqual(select_gear(**{**BASE,"evidence_quality":0.2}).selected_gear,"G1")
    def test_uncertainty_downshifts(self): self.assertEqual(select_gear(**{**BASE,"uncertainty":0.8}).selected_gear,"G1")
    def test_storage_pressure_brakes(self):
        d=select_gear(**{**BASE,"storage_pressure_ratio":0.96}); self.assertEqual((d.selected_gear,d.guard_status),("G1","HUMAN_GATE"))
    def test_moderate_storage_caps_heavy_gear(self): self.assertIn(select_gear(**{**BASE,"task_complexity":1.0,"storage_pressure_ratio":0.90}).selected_gear,{"G2","G3","G4"})
    def test_roster_cannot_create_lcr_d(self):
        validate_formal_roster({"LCR-A":{},"LCR-B":{},"LCR-C":{}})
        with self.assertRaises(GearboxGuardError): validate_formal_roster({"LCR-A":{},"LCR-B":{},"LCR-C":{},"LCR-D":{}})
    def test_owner_input_does_not_drop_active_rpm(self):
        before=ACTIVE_STATE(); after,meta=capture_owner_input_without_rpm_drop(before,{"source":"owner","body":"new priority idea"})
        for key in ("mission_id","status","step_id","current_role","pending_packet","pending_packet_sha256","lease"):
            self.assertEqual(after[key],before[key])
        self.assertNotIn("body",meta); self.assertEqual(len(meta["body_sha256"]),64)
    def test_torque_state_is_compact_and_excludes_raw_chat(self):
        compact=compact_torque_state(ACTIVE_STATE())
        self.assertEqual(compact["mission_id"],"LCR-EVOLUTION-0005"); self.assertNotIn("raw_chat",compact); self.assertEqual(len(compact["state_fingerprint"]),64)
    def test_g1_to_g2_clutch_overlap_holds_sender_until_ack(self):
        state=ACTIVE_STATE(); first=overlap_shift(active_state=state,from_gear="G1",to_gear="G2")
        self.assertEqual(first["shift_status"],"CLUTCH_OVERLAP"); self.assertTrue(first["sender_torque_held"]); self.assertTrue(first["original_atomic_work_alive"])
        ack=first["compact_state"]["state_fingerprint"]
        second=overlap_shift(active_state=state,from_gear="G1",to_gear="G2",receiver_state_fingerprint=ack)
        self.assertEqual(second["shift_status"],"SHIFT_COMPLETE"); self.assertFalse(second["sender_torque_held"]); self.assertTrue(second["receiver_acknowledged"])
    def test_g2_to_g1_downshift_engages_lower_guard_before_release(self):
        state=ACTIVE_STATE(); first=overlap_shift(active_state=state,from_gear="G2",to_gear="G1",downshift=True)
        self.assertTrue(first["lower_guard_engaged"]); self.assertFalse(first["higher_gear_released"])
        ack=first["compact_state"]["state_fingerprint"]
        second=overlap_shift(active_state=state,from_gear="G2",to_gear="G1",receiver_state_fingerprint=ack,downshift=True)
        self.assertTrue(second["lower_guard_engaged"]); self.assertTrue(second["higher_gear_released"]); self.assertEqual(second["shift_status"],"DOWNSHIFT_COMPLETE")

if __name__ == "__main__": unittest.main()
