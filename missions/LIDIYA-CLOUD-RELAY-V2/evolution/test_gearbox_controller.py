import unittest

from gearbox_controller import GearboxGuardError, select_gear, validate_formal_roster

BASE = dict(risk="LOW", uncertainty=0.1, evidence_quality=0.9, task_complexity=0.5, reversibility=True, contradiction=False, hard_safety_conflict=False, rollback_required=False, standby=False, storage_pressure_ratio=0.1, proposed_autonomy=6)

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

if __name__ == "__main__": unittest.main()
