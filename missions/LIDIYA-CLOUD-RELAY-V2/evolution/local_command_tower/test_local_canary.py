import json,os,tempfile,unittest,uuid
from pathlib import Path
from local_canary import run_isolated_canary,run_windows_owner_canary,load_installation_metadata,CanaryError,_hash

class CanaryTests(unittest.TestCase):
    def _meta(self,root,**changes):
        d={"schema_version":"1.0","installation_id":"11111111-1111-4111-8111-111111111111","install_root":str(root),"created_at":"2026-08-15T00:00:00Z","component":"LIDIYA-LOCAL-NAV-COMMAND-TOWER-TYPE-1","transport":"LOOPBACK_AND_WORKSPACE_SPOOL","privilege":"USER_SPACE"}; d.update(changes); return d
    def test_isolated_full_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_isolated_canary(Path(d)); self.assertEqual(r["wake_state"],"READY"); self.assertEqual(r["command_exit_code"],0); self.assertEqual(r["duplicate_disposition"],"ALREADY_EXECUTED_NOOP"); self.assertEqual(r["executor_calls"],1); self.assertEqual(r["wrong_resume"],"HOLD_FINGERPRINT_MISMATCH"); self.assertEqual(r["matching_resume"],"RESUMED"); self.assertFalse(r["owner_machine_touched"]); self.assertEqual(r["promotion_status"],"CANARY_CANDIDATE_ONLY")
    def test_install_metadata_binding(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); (root/".lidiya").mkdir(); meta=self._meta(root); (root/".lidiya"/"installation.json").write_text(json.dumps(meta),encoding="utf-8"); loaded=load_installation_metadata(root); self.assertEqual(loaded["installation_id"],meta["installation_id"]); self.assertEqual(len(_hash(loaded)),64)
    def test_missing_install_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CanaryError): load_installation_metadata(Path(d).resolve())
    def test_invalid_uuid(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); (root/".lidiya").mkdir(); (root/".lidiya"/"installation.json").write_text(json.dumps(self._meta(root,installation_id="x")),encoding="utf-8")
            with self.assertRaises(CanaryError): load_installation_metadata(root)
    def test_install_root_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); (root/".lidiya").mkdir(); (root/".lidiya"/"installation.json").write_text(json.dumps(self._meta(root,install_root=str(root/"other"))),encoding="utf-8")
            with self.assertRaises(CanaryError): load_installation_metadata(root)
    def test_privilege_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); (root/".lidiya").mkdir(); (root/".lidiya"/"installation.json").write_text(json.dumps(self._meta(root,privilege="ADMIN")),encoding="utf-8")
            with self.assertRaises(CanaryError): load_installation_metadata(root)
    def test_transport_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); (root/".lidiya").mkdir(); (root/".lidiya"/"installation.json").write_text(json.dumps(self._meta(root,transport="PUBLIC")),encoding="utf-8")
            with self.assertRaises(CanaryError): load_installation_metadata(root)
    @unittest.skipIf(os.name=="nt","non-Windows gate test")
    def test_windows_owner_mode_rejected_off_windows(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CanaryError): run_windows_owner_canary(d)
if __name__=="__main__": unittest.main()
