import json,tempfile,unittest
from pathlib import Path
from evidence_reconciler import AUTH_REF,sha256_json
from local_evidence_bundle import BundleError,build_local_evidence_bundle,verify_bundle

class BundleTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.root=Path(self.t.name).resolve(); self.l=self.root/".lidiya"; self.l.mkdir()
        self.meta={"schema_version":"1.0","installation_id":"11111111-1111-4111-8111-111111111111","install_root":str(self.root),"created_at":"2026-08-15T00:00:00Z","component":"LIDIYA-LOCAL-NAV-COMMAND-TOWER-TYPE-1","transport":"LOOPBACK_AND_WORKSPACE_SPOOL","privilege":"USER_SPACE"}
        self.can={"mode":"WINDOWS_FIXED_HARMLESS_ECHO","command_id":"LOCAL-CANARY-ECHO-001","stdout":"LIDIYA_CANARY\n","stderr":"","exit_code":0,"evidence_sha256":"e"*64,"authorization_ref":AUTH_REF,"arbitrary_command_input":False,"installation_id":self.meta["installation_id"],"installation_fingerprint":sha256_json(self.meta),"install_root":str(self.root),"provenance":{"source":"LOCAL_OWNER_WINDOWS_EXECUTION","observed_by":"LOCAL_CANARY"},"promotion_status":"REAL_LOCAL_CANARY_EVIDENCE_CANDIDATE_UNATTESTED"}; self.can["canary_sha256"]=sha256_json(self.can)
        self.write()
    def tearDown(self): self.t.cleanup()
    def write(self):
        (self.l/"installation.json").write_text(json.dumps(self.meta),encoding="utf-8"); (self.l/"local_canary_evidence.json").write_text(json.dumps(self.can),encoding="utf-8")
    def test_build_verify_and_write(self):
        b=build_local_evidence_bundle(self.root); self.assertTrue(verify_bundle(b)); self.assertFalse(b["E3_promoted"]); self.assertTrue((self.l/"outbox/local_evidence_bundle.json").is_file())
    def test_repeat_export_idempotent_hash(self):
        a=build_local_evidence_bundle(self.root); b=build_local_evidence_bundle(self.root); self.assertEqual(a["bundle_sha256"],b["bundle_sha256"])
    def test_missing_canary(self):
        (self.l/"local_canary_evidence.json").unlink()
        with self.assertRaises(BundleError): build_local_evidence_bundle(self.root)
    def test_tampered_canary(self):
        self.can["stdout"]="BAD\n"; self.write()
        with self.assertRaises(BundleError): build_local_evidence_bundle(self.root)
    def test_wrong_auth(self):
        self.can["authorization_ref"]="wrong"; self.can["canary_sha256"]=sha256_json(self.can); self.write()
        with self.assertRaises(BundleError): build_local_evidence_bundle(self.root)
    def test_raw_chat_rejected(self):
        self.can["raw_chat"]="no"; self.can["canary_sha256"]=sha256_json(self.can); self.write()
        with self.assertRaises(BundleError): build_local_evidence_bundle(self.root)
    def test_secret_like_key_rejected(self):
        self.meta["api_token"]="x"; self.write()
        with self.assertRaises(BundleError): build_local_evidence_bundle(self.root)
    def test_bundle_hash_tamper_rejected(self):
        b=build_local_evidence_bundle(self.root,write=False); b["installation_id"]="22222222-2222-4222-8222-222222222222"
        with self.assertRaises(BundleError): verify_bundle(b)
    def test_premature_E3_rejected(self):
        b=build_local_evidence_bundle(self.root,write=False); body={k:v for k,v in b.items() if k!="bundle_sha256"}; body["E3_promoted"]=True; body["bundle_sha256"]=sha256_json(body)
        with self.assertRaises(BundleError): verify_bundle(body)
    def test_setup_script_static_policy(self):
        sn=Path(__file__).resolve().parent.parent/"small_nest"
        text=(sn/"SETUP_SMALL_NEST.ps1").read_text(encoding="utf-8").lower()
        self.assertIn("http://127.0.0.1:8765/health",text)
        self.assertIn("run_local_canary.cmd",text)
        self.assertIn("export_local_evidence.ps1",text)
        self.assertNotIn("-verb runas",text)
        for bad in ("new-service","sc.exe create","schtasks","new-netfirewallrule","set-netfirewall","reg add","0.0.0.0","https://"):
            self.assertNotIn(bad,text)
    def test_setup_has_no_parameters_or_arbitrary_command_input(self):
        sn=Path(__file__).resolve().parent.parent/"small_nest"
        text=(sn/"SETUP_SMALL_NEST.ps1").read_text(encoding="utf-8").lower()
        self.assertNotIn("param(",text)
        self.assertNotIn("read-host",text)
        self.assertNotIn("invoke-expression",text)
    def test_export_script_fixed_local_paths_no_network(self):
        sn=Path(__file__).resolve().parent.parent/"small_nest"
        text=(sn/"EXPORT_LOCAL_EVIDENCE.ps1").read_text(encoding="utf-8").lower()
        self.assertNotIn("http://",text); self.assertNotIn("https://",text); self.assertNotIn("invoke-webrequest",text)
        self.assertIn("local_evidence_bundle.py",text)
        self.assertNotIn("param(",text)
if __name__=="__main__": unittest.main()
