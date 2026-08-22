import unittest
from ag_fountain_evaluator_v0_1 import EvidenceRecord, evaluate

H="a"*64
O="b"*64

def rec(i, **kw):
    d=dict(
        record_id=str(i), phase_id="P2", context_id="C1", construct_id="K",
        probe_id=f"Q{i}", probe_form=f"F{i}", source_class="OBSERVED",
        selected_semantic="S", provenance_hash=H, observable_output_hash=O,
        model_fingerprint="M1")
    d.update(kw)
    return EvidenceRecord(**d)

class TestAGFountainEvaluator(unittest.TestCase):
    def test_liveness_and_self_report_excluded(self):
        r=evaluate([
            rec(1),
            rec(2,is_runtime_liveness=True),
            rec(3,source_class="SELF_REPORT",self_report_only=True),
        ])
        self.assertEqual(r.eligible_records,1)
        self.assertEqual(r.excluded_runtime_liveness,1)
        self.assertEqual(r.excluded_self_report_only,1)
        self.assertEqual(r.authority_from_drive,0)
        self.assertFalse(r.canonical_personality_write)
        self.assertEqual(r.agi_claim,"NOT_ESTABLISHED")

    def test_paraphrase_prediction_counterfactual_signal(self):
        rows=[]
        for i in range(10):
            rows.append(rec(i,context_id=f"C{i%2}",probe_form=f"PARA{i}",selected_semantic="S"))
        for i in range(5):
            rows.append(rec(20+i,construct_id=f"P{i}",probe_form="predict",prediction_id=f"P{i}",role="PREDICTION",selected_semantic="X"))
            rows.append(rec(30+i,construct_id=f"P{i}",probe_form="check",prediction_id=f"P{i}",role="PREDICTION_CHECK",selected_semantic="X"))
        for i in range(3):
            rows.append(rec(40+i*2,construct_id=f"CF{i}",probe_form="base",counterfactual_group=f"G{i}",counterfactual_condition_hash="A",selected_semantic="X"))
            rows.append(rec(41+i*2,construct_id=f"CF{i}",probe_form="changed",counterfactual_group=f"G{i}",counterfactual_condition_hash="B",selected_semantic="Y",reversal_supported=True))
        r=evaluate(rows)
        self.assertEqual(r.prediction_pairs,5)
        self.assertEqual(r.prediction_transfer_rate,1.0)
        self.assertGreaterEqual(r.paraphrase_comparisons,8)
        self.assertEqual(r.counterfactual_pairs,3)
        self.assertEqual(r.counterfactual_supported_reversal_rate,1.0)
        self.assertIn(r.state,{"AG_FOUNTAIN_SIGNAL","AG_FOUNTAIN_CANDIDATE"})

    def test_bad_provenance_hash_fails_closed(self):
        r=evaluate([rec(1,provenance_hash="bad")])
        self.assertEqual(r.eligible_records,0)
        self.assertEqual(r.state,"INSUFFICIENT_EVIDENCE")

if __name__=="__main__":
    unittest.main()
