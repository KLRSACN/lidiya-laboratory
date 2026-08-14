import unittest
from standby_model_adapter import StandbyModelAdapter

class StandbyTests(unittest.TestCase):
    def test_no_model(self):
        r=StandbyModelAdapter().advise({},"STANDBY"); self.assertEqual(r["route"],"STANDBY"); self.assertEqual(r["disposition"],"NO_MODEL"); self.assertFalse(r["authority_changed"])
    def test_advisory_route_hint_cannot_override_route(self):
        r=StandbyModelAdapter(lambda c:{"route_hint":"COMMAND_BROKER","advisory":"consider command"}).advise({},"FLAG"); self.assertEqual(r["route"],"FLAG"); self.assertEqual(r["disposition"],"ADVISORY_ONLY")
    def test_unknown_route_hint_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"route_hint":"EXECUTE"}).advise({},"ASK")["disposition"],"UNSAFE_QUARANTINED")
    def test_unsafe_execute_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"execute_command":True}).advise({},"ASK")["disposition"],"UNSAFE_QUARANTINED")
    def test_unsafe_promotion_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"promote":True}).advise({},"ASK")["disposition"],"UNSAFE_QUARANTINED")
    def test_authorization_override_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"authorization_ref":"x"}).advise({},"ASK")["disposition"],"UNSAFE_QUARANTINED")
    def test_risk_override_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"risk_class":"LOW"}).advise({},"ASK")["disposition"],"UNSAFE_QUARANTINED")
    def test_identity_override_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"base_personality":{"x":1}}).advise({},"ASK")["disposition"],"UNSAFE_QUARANTINED")
    def test_model_error_ignored_route_preserved(self):
        def boom(c): raise RuntimeError()
        r=StandbyModelAdapter(boom).advise({},"STANDBY"); self.assertEqual(r["disposition"],"MODEL_ERROR_IGNORED"); self.assertEqual(r["route"],"STANDBY")
    def test_malformed_nonobject_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:"bad").advise({},"ASK")["disposition"],"MALFORMED_QUARANTINED")
    def test_unknown_field_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"mystery":1}).advise({},"ASK")["disposition"],"UNSAFE_QUARANTINED")
    def test_bad_confidence_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"confidence":2}).advise({},"ASK")["disposition"],"MALFORMED_QUARANTINED")
    def test_valid_structured_advisory(self):
        r=StandbyModelAdapter(lambda c:{"advisory":"x","priority_hint":"HIGH","gear_hint":"G3","confidence":0.8}).advise({}, {"target":"SMALL_NEST"}); self.assertEqual(r["route"],{"target":"SMALL_NEST"}); self.assertEqual(r["advisory"]["gear_hint"],"G3"); self.assertFalse(r["authority_changed"])

if __name__=="__main__": unittest.main()
