import os, tempfile, unittest
from pathlib import Path
from local_canary import run_isolated_canary, run_windows_owner_canary, CanaryError

class CanaryTests(unittest.TestCase):
    def test_isolated_full_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_isolated_canary(Path(d)); self.assertEqual(r["wake_state"],"READY"); self.assertEqual(r["command_exit_code"],0); self.assertEqual(r["duplicate_disposition"],"ALREADY_EXECUTED_NOOP"); self.assertEqual(r["executor_calls"],1); self.assertEqual(r["wrong_resume"],"HOLD_FINGERPRINT_MISMATCH"); self.assertEqual(r["matching_resume"],"RESUMED"); self.assertFalse(r["owner_machine_touched"]); self.assertEqual(len(r["canary_sha256"]),64)
    @unittest.skipIf(os.name=="nt","non-Windows gate test")
    def test_windows_owner_mode_rejected_off_windows(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CanaryError): run_windows_owner_canary(d)

if __name__=="__main__": unittest.main()
