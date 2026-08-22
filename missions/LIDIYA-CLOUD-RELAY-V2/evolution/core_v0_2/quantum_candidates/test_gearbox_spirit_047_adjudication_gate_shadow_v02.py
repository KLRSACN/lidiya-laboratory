import unittest
from gearbox_spirit_047_adjudication_gate_shadow_v02 import SpiritAdjudicationGateError, terminal_exit_engineering_gate

def valid():
    return {
        "mission_id":"LCR-EVOLUTION-0005","step_id":9,"candidate_version":"V05",
        "spirit_review_id":"SPIRIT-GEARBOX-V2.1-FRESH-V05","spirit_review_blob_sha":"1"*40,
        "reviewed_candidate_version":"V05","veto_id":"SPIRIT-MOD-GB21-047",
        "disposition":"CLOSED_FOR_NONFORMAL_TERMINAL_EXIT_ENGINEERING","higher_high_veto_open":False,
        "evidence_binding_status":"EXACT_CURRENT_NONFORMAL_EXECUTABLE_EVIDENCE_BOUND",
        "v05_source_sha":"9aaf3ad9f673944d548e2cd880c9286b98e72704",
        "v05_test_sha":"a4c98981561cf8c310c66c03367aa8fbf3954d61",
        "v05_contract_sha":"df4753a9eaa7d734afb81a7e32d7efb3fa6617b7",
        "workflow_run_id":32524738088,"workflow_job_id":96904287434,"executed_regression_total":27,
        "terminal_exit_activation_allowed":True,"formal_effect":"NONE","c_pass_claimed":False,
    }

class Spirit047AdjudicationGateV02Tests(unittest.TestCase):
    def test_exact_bound_fresh_review_can_open_nonformal_gate(self):
        x=terminal_exit_engineering_gate(valid())
        self.assertEqual(x["gate"],"OPEN_FOR_NONFORMAL_TERMINAL_EXIT_ENGINEERING")
        self.assertEqual(x["experience_delta"],0); self.assertEqual(x["personality_delta"],0)
    def test_review_blob_identity_required(self):
        x=valid(); x["spirit_review_blob_sha"]="bad"
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)
    def test_v05_source_substitution_rejected(self):
        x=valid(); x["v05_source_sha"]="0"*40
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)
    def test_v05_test_substitution_rejected(self):
        x=valid(); x["v05_test_sha"]="0"*40
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)
    def test_v05_contract_substitution_rejected(self):
        x=valid(); x["v05_contract_sha"]="0"*40
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)
    def test_run_job_substitution_rejected(self):
        x=valid(); x["workflow_job_id"]+=1
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)
    def test_partial_regression_count_rejected(self):
        x=valid(); x["executed_regression_total"]=26
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)
    def test_open_or_higher_veto_rejected(self):
        x=valid(); x["higher_high_veto_open"]=True
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)
    def test_formal_claim_rejected(self):
        x=valid(); x["c_pass_claimed"]=True
        with self.assertRaises(SpiritAdjudicationGateError): terminal_exit_engineering_gate(x)

if __name__ == "__main__": unittest.main()
