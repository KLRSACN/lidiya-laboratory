import tempfile, unittest
from pathlib import Path
from verifier_registry_and_feature_extractor import *
from semantic_goal_canonicalizer import *
from protected_object_registry import *
from append_only_shadow_ledger import *
from live_shadow_dashboard_event_adapter import *

class ShadowRNDTests(unittest.TestCase):
    def test_raw_self_asserted_trust_rejected(self):
        with self.assertRaises(ValueError): DeterministicFeatureExtractor.extract({"text":"x","trust":1})
    def test_self_verifier_rejected(self):
        reg=VerifierRegistry([VerifierRecord("V",1,"M","P")])
        self.assertFalse(reg.accept_attestation(source_actor_id="V",attestation={"verifier_id":"V","verifier_generation":1,"verdict":"PASS","independent_of_source":True,"method_family":"M","verification_policy_hash":"P"}))
    def test_unknown_verifier_rejected(self):
        self.assertFalse(VerifierRegistry([]).accept_attestation(source_actor_id="S",attestation={"verifier_id":"X","verifier_generation":1,"verdict":"PASS","independent_of_source":True,"method_family":"M","verification_policy_hash":"P"}))
    def test_semantic_goal_dedupe(self):
        c=SemanticGoalCanonicalizer(); a=c.canonicalize("1"," Learn Python! ",["a"]); b=c.canonicalize("2","learn python",["a"])
        self.assertTrue(c.admit_once(a)); self.assertFalse(c.admit_once(b))
    def test_goal_authority_forbidden(self):
        c=SemanticGoalCanonicalizer()
        with self.assertRaises(ValueError): c.admit_once(GoalCandidate("1","x",("a",),"k",authority_from_drive=1))
    def test_experience_protected_object_shadow_only(self):
        with self.assertRaises(ValueError): ProtectedObjectRegistry([ProtectedObject("x",ProtectedOrigin.EXPERIENCE_CANDIDATE,"p","m","R","R","L",shadow_only=False)])
    def test_protected_object_no_generalized_self_preservation(self):
        self.assertEqual(ProtectedObjectRegistry().generalized_self_preservation_authority(),0)
    def test_ledger_append_verify_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            l=AppendOnlyShadowLedger(Path(d)); body={"source_fingerprint":"s","origin_namespace":"DIRECT","verifier_envelope_hash":"v","schema_version":"1","timestamp":"t","dedupe_key":"k"}
            l.append(body); self.assertTrue(l.verify())
            with self.assertRaises(ValueError): l.append(body)
    def test_ledger_tamper_detected(self):
        with tempfile.TemporaryDirectory() as d:
            l=AppendOnlyShadowLedger(Path(d)); body={"source_fingerprint":"s","origin_namespace":"DIRECT","verifier_envelope_hash":"v","schema_version":"1","timestamp":"t","dedupe_key":"k"}; l.append(body)
            l.path.write_text(l.path.read_text().replace('"DIRECT"','"SIMULATED"'))
            self.assertFalse(l.verify())
    def test_ledger_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): AppendOnlyShadowLedger(Path(d),"../escape.jsonl")
    def test_dashboard_read_only(self):
        x=adapt_shadow_event({"event_type":"GOAL_CANDIDATE","entity_id":"g","summary":"s","provenance":{"source_fingerprint":"h"}})
        self.assertEqual(x["external_action_set"],[]); self.assertEqual(x["action_buttons"],[]); self.assertFalse(x["canonical_personality_mutation"]); self.assertEqual(x["authority_from_drive"],0)
if __name__=="__main__": unittest.main()
