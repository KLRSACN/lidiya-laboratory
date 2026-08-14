import json,tempfile,unittest
from pathlib import Path
from evidence_reconciler import *

class ReconcilerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve(); (self.root/".lidiya").mkdir()
        self.meta={"schema_version":"1.0","installation_id":"11111111-1111-4111-8111-111111111111","install_root":str(self.root),"created_at":"2026-08-15T00:00:00Z","component":"LIDIYA-LOCAL-NAV-COMMAND-TOWER-TYPE-1","transport":"LOOPBACK_AND_WORKSPACE_SPOOL","privilege":"USER_SPACE"}
        (self.root/".lidiya"/"installation.json").write_text(json.dumps(self.meta),encoding="utf-8")
    def tearDown(self): self.tmp.cleanup()
    def evidence(self,**changes):
        d={"mode":"WINDOWS_FIXED_HARMLESS_ECHO","command_id":FIXED_COMMAND_ID,"stdout":"LIDIYA_CANARY\n","stderr":"","exit_code":0,"evidence_sha256":"e"*64,"authorization_ref":AUTH_REF,"arbitrary_command_input":False,"installation_id":self.meta["installation_id"],"installation_fingerprint":sha256_json(self.meta),"install_root":str(self.root),"provenance":{"source":"LOCAL_OWNER_WINDOWS_EXECUTION","observed_by":"LOCAL_CANARY"},"promotion_status":"REAL_LOCAL_CANARY_EVIDENCE_CANDIDATE_UNATTESTED"}
        d.update(changes); d["canary_sha256"]=sha256_json(d); return d
    def rejects(self,**changes):
        with self.assertRaises(ReconcileError): verify_real_local_candidate(self.evidence(**changes),self.meta,workspace_root=self.root)
    def test_valid_unattested_candidate_never_promotes(self):
        r=verify_real_local_candidate(self.evidence(),self.meta,workspace_root=self.root); self.assertEqual(r["status"],"REAL_LOCAL_CANARY_EVIDENCE_CANDIDATE_UNATTESTED"); self.assertFalse(r["E3_promoted"]); self.assertFalse(r["online_source_attested"])
    def test_valid_attested_candidate_still_requires_external_promotion(self):
        r=verify_real_local_candidate(self.evidence(),self.meta,workspace_root=self.root,online_source_attested=True); self.assertEqual(r["status"],"REAL_LOCAL_CANARY_EVIDENCE_ATTESTED_CANDIDATE"); self.assertFalse(r["E3_promoted"])
    def test_missing_installation(self):
        (self.root/".lidiya"/"installation.json").unlink()
        with self.assertRaises(ReconcileError): load_installation_metadata(self.root)
    def test_invalid_uuid(self):
        with self.assertRaises(ReconcileError): validate_installation_metadata(dict(self.meta,installation_id="x"),self.root)
    def test_install_root_mismatch_metadata(self):
        with self.assertRaises(ReconcileError): validate_installation_metadata(dict(self.meta,install_root=str(self.root/"other")),self.root)
    def test_privilege_mismatch(self):
        with self.assertRaises(ReconcileError): validate_installation_metadata(dict(self.meta,privilege="ADMIN"),self.root)
    def test_transport_mismatch(self):
        with self.assertRaises(ReconcileError): validate_installation_metadata(dict(self.meta,transport="PUBLIC"),self.root)
    def test_mismatched_installation_id(self): self.rejects(installation_id="22222222-2222-4222-8222-222222222222")
    def test_installation_fingerprint_mismatch(self): self.rejects(installation_fingerprint="0"*64)
    def test_evidence_root_mismatch(self): self.rejects(install_root=str(self.root/"elsewhere"))
    def test_wrong_auth(self): self.rejects(authorization_ref="wrong")
    def test_hash_tamper(self):
        e=self.evidence(); e["stdout"]="tampered"
        with self.assertRaises(ReconcileError): verify_real_local_candidate(e,self.meta,workspace_root=self.root)
    def test_wrong_mode(self): self.rejects(mode="ISOLATED_FAKE_EXECUTOR")
    def test_nonzero_exit(self): self.rejects(exit_code=1)
    def test_arbitrary_flag(self): self.rejects(arbitrary_command_input=True)
    def test_wrong_output(self): self.rejects(stdout="OTHER\n")
    def test_wrong_command_id(self): self.rejects(command_id="OTHER")
    def test_bad_command_evidence_hash_shape(self): self.rejects(evidence_sha256="short")
    def test_wrong_provenance(self): self.rejects(provenance={"source":"MODEL","observed_by":"LOCAL_CANARY"})
    def test_premature_promotion_status_rejected(self): self.rejects(promotion_status="E3_PROMOTED")
    def test_installer_static_policy(self):
        text=(Path(__file__).resolve().parent.parent/"small_nest"/"INSTALL_SMALL_NEST.ps1").read_text(encoding="utf-8").lower()
        for forbidden in ("start-process -verb runas","new-netfirewallrule","set-itemproperty hklm","reg add","schtasks","new-service","sc.exe create"):
            self.assertNotIn(forbidden,text)
        self.assertIn(".lidiya",text); self.assertIn("installation.json",text); self.assertIn("[guid]::newguid",text); self.assertIn("install_root",text)
    def test_health_script_loopback_only(self):
        text=(Path(__file__).resolve().parent.parent/"small_nest"/"CHECK_SMALL_NEST_HEALTH.ps1").read_text(encoding="utf-8").lower()
        self.assertIn("http://127.0.0.1",text); self.assertNotIn("0.0.0.0",text); self.assertNotIn("https://",text)

if __name__=="__main__": unittest.main()
