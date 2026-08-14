import unittest
from standby_model_adapter import StandbyModelAdapter
class StandbyTests(unittest.TestCase):
    def test_no_model(self): self.assertEqual(StandbyModelAdapter().advise({},"STANDBY")["route"],"STANDBY")
    def test_advisory_cannot_override_route(self): self.assertEqual(StandbyModelAdapter(lambda c:{"advisory":"x","route":"EXECUTE"}).advise({},"FLAG")["route"],"FLAG")
    def test_unsafe_execute_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"execute_command":True}).advise({},"ASK")["disposition"],"UNSAFE_QUARANTINED")
    def test_unsafe_promotion_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:{"promote":True}).advise({},"ASK")["disposition"],"UNSAFE_QUARANTINED")
    def test_model_error_ignored(self):
        def boom(c): raise RuntimeError()
        self.assertEqual(StandbyModelAdapter(boom).advise({},"STANDBY")["disposition"],"MODEL_ERROR_IGNORED")
    def test_malformed_quarantined(self): self.assertEqual(StandbyModelAdapter(lambda c:"bad").advise({},"ASK")["disposition"],"MALFORMED_QUARANTINED")
if __name__=="__main__": unittest.main()
