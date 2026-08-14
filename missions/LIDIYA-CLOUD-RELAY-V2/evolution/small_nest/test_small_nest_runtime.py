import tempfile, unittest
from pathlib import Path
from runtime import SmallNestRuntime

class SmallNestTests(unittest.TestCase):
    def setUp(self): self.td=tempfile.TemporaryDirectory(); self.rt=SmallNestRuntime(Path(self.td.name)/"state.json")
    def tearDown(self): self.td.cleanup()
    def test_wake_and_health(self):
        self.rt.wake(); h=self.rt.health(); self.assertEqual(h["runtime_state"],"READY"); self.assertFalse(h["offline_held"])
    def test_offline_hold_and_matching_resume(self):
        self.rt.wake(); self.rt.hold_offline("fp1"); self.assertEqual(self.rt.reconnect("fp1")["status"],"RESUMED")
    def test_offline_hold_rejects_wrong_fingerprint(self):
        self.rt.hold_offline("fp1"); self.assertEqual(self.rt.reconnect("wrong")["status"],"HOLD_FINGERPRINT_MISMATCH")
    def test_state_persists_across_runtime_restart(self):
        self.rt.wake(); rt2=SmallNestRuntime(self.rt.store.path); self.assertEqual(rt2.health()["runtime_state"],"READY")

if __name__=="__main__": unittest.main()
