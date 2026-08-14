import json,os,tempfile,unittest
from pathlib import Path
from local_canary import run_isolated_canary,run_windows_owner_canary,load_installation_metadata,CanaryError
class CanaryTests(unittest.TestCase):
    def test_isolated_full_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_isolated_canary(Path(d)); self.assertEqual(r["wake_state"],"READY"); self.assertEqual(r["command_exit_code"],0); self.assertEqual(r["duplicate_disposition"],"ALREADY_EXECUTED_NOOP"); self.assertEqual(r["executor_calls"],1); self.assertEqual(r["wrong_resume"],"HOLD_FINGERPRINT_MISMATCH"); self.assertEqual(r["matching_resume"],"RESUMED"); self.assertFalse(r["owner_machine_touched"]); self.assertEqual(r["promotion_status"],"CANARY_CANDIDATE_ONLY")
    def test_install_metadata_binding(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); (root/".lidiya").mkdir(); iid="11111111-1111-4111-8111-111111111111"; (root/".lidiya"/"installation.json").write_text(json.dumps({"installation_id":iid,"workspace_root":str(root),"secrets_present":False}),encoding="utf-8"); self.assertEqual(load_installation_metadata(root)["installation_id"],iid)
    def test_missing_install_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CanaryError): load_installation_metadata(Path(d).resolve())
    def test_workspace_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); (root/".lidiya").mkdir(); (root/".lidiya"/"installation.json").write_text(json.dumps({"installation_id":"x","workspace_root":str(root/"other"),"secrets_present":False}),encoding="utf-8");
            with self.assertRaises(CanaryError): load_installation_metadata(root)
    @unittest.skipIf(os.name=="nt","non-Windows gate test")
    def test_windows_owner_mode_rejected_off_windows(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CanaryError): run_windows_owner_canary(d)
if __name__=="__main__": unittest.main()
