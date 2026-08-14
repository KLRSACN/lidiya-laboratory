import math, unittest
from memory_weight_lab import DIMENSIONS, WeightLabError, apply_overlay, fingerprint

class WeightLabTests(unittest.TestCase):
    def base(self): return {k:0.5 for k in DIMENSIONS}
    def test_reversible_overlay_does_not_mutate_input(self):
        base=self.base(); before=dict(base); r=apply_overlay(base,{"W_novelty":0.1,"W_motivation":-0.1},experiment_id="e1"); self.assertEqual(base,before); self.assertFalse(r["canonical_base_mutated"]); self.assertEqual(r["promotion_status"],"CANDIDATE_ONLY"); self.assertEqual(r["rollback"]["restore_base_fingerprint"],fingerprint(before))
    def test_exact_13_dimension_base_required(self):
        b=self.base(); b.pop("W_goal")
        with self.assertRaises(WeightLabError): apply_overlay(b,{})
    def test_unknown_overlay_dimension_rejected(self):
        with self.assertRaises(WeightLabError): apply_overlay(self.base(),{"W_unknown":0.1})
    def test_nan_rejected(self):
        with self.assertRaises(WeightLabError): apply_overlay(self.base(),{"W_emotion":math.nan})
    def test_infinite_rejected(self):
        with self.assertRaises(WeightLabError): apply_overlay(self.base(),{"W_emotion":math.inf})
    def test_delta_above_bound_rejected(self):
        with self.assertRaises(WeightLabError): apply_overlay(self.base(),{"W_emotion":0.26})
    def test_effective_clips_without_base_mutation(self):
        b=self.base(); b["W_emotion"]=0.9; r=apply_overlay(b,{"W_emotion":0.2}); self.assertEqual(r["effective"]["W_emotion"],1.0); self.assertEqual(b["W_emotion"],0.9)
    def test_fingerprints_deterministic(self):
        a=apply_overlay(self.base(),{"W_self":0.1},experiment_id="x"); b=apply_overlay(self.base(),{"W_self":0.1},experiment_id="x"); self.assertEqual(a["record_fingerprint"],b["record_fingerprint"])
    def test_overlay_order_does_not_change_fingerprint(self):
        a=apply_overlay(self.base(),{"W_self":0.1,"W_goal":-0.05}); b=apply_overlay(self.base(),{"W_goal":-0.05,"W_self":0.1}); self.assertEqual(a["overlay_fingerprint"],b["overlay_fingerprint"])

if __name__=="__main__": unittest.main()
