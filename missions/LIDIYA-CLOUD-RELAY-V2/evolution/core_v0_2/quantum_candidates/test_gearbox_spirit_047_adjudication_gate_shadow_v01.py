import unittest
from gearbox_spirit_047_adjudication_gate_shadow_v01 import SpiritAdjudicationGateError, terminal_exit_engineering_gate


def valid():
    return {
        "mission_id":"LCR-EVOLUTION-0005","step_id":9,"candidate_version":"V05",
        "spirit_review_id":"SPIRIT-GEARBOX-V2.1-FRESH-V05","reviewed_candidate_version":"V05",
        "veto_id":"SPIRIT-MOD-GB21-047","disposition":"CLOSED_FOR_NONFORMAL_TERMINAL_EXIT_ENGINEERING",
        "higher_high_veto_open":False,"evidence_binding_status":"EXACT_CURRENT_NONFORMAL_EXECUTABLE_EVIDENCE_BOUND",
        "terminal_exit_activation_allowed":True,"formal_effect":"NONE","c_pass_claimed":False,
    }


class Spirit047AdjudicationGateTests(unittest.TestCase):
    def test_fresh_exact_v05_closed_adjudication_opens_nonformal_gate(self):
        x=terminal_exit_engineering_gate(valid())
        self.assertEqual(x["gate"],"OPEN_FOR_NONFORMAL_TERMINAL_EXIT_ENGINEERING")
        self.assertEqual(x["experience_delta"],0)
        self.assertEqual(x["personality_delta"],0)
        self.assertFalse(x["p_base_mutation_allowed"])

    def test_v04_era_review_cannot_activate_v05_terminal_exit(self):
        x=valid(); x["reviewed_candidate_version"]="V04"
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)

    def test_open_047_cannot_activate(self):
        x=valid(); x["disposition"]="STILL_OPEN"
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)

    def test_higher_high_veto_cannot_activate(self):
        x=valid(); x["higher_high_veto_open"]=True
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)

    def test_unbound_evidence_cannot_activate(self):
        x=valid(); x["evidence_binding_status"]="EVIDENCE_VISIBILITY_GAP"
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)

    def test_formal_claim_cannot_cross_shadow_gate(self):
        x=valid(); x["c_pass_claimed"]=True
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)

    def test_explicit_activation_required(self):
        x=valid(); x["terminal_exit_activation_allowed"]=False
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)


if __name__ == "__main__": unittest.main()
