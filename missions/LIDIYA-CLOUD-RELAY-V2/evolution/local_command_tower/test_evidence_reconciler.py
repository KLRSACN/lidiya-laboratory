import json,tempfile,unittest
from pathlib import Path
from evidence_reconciler import *
class ReconcilerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); (self.root/".lidiya").mkdir()
        self.meta={"installation_id":"11111111-1111-4111-8111-111111111111","workspace_root":str(self.root),"secrets_present":False}
        (self.root/".lidiya"/"installation.json").write_text(json.dumps(self.meta),encoding="utf-8")
    def tearDown(self): self.tmp.cleanup()
    def evidence(self,**changes):
        d={"mode":"WINDOWS_FIXED_HARMLESS_ECHO","command_id":FIXED_COMMAND_ID,"stdout":"LIDIYA_CANARY\n","stderr":"","exit_code":0,"evidence_sha256":"e"*64,"authorization_ref":AUTH_REF,"arbitrary_command_input":False,"installation_id":self.meta["installation_id"],"provenance":{"source":"LOCAL_OWNER_WINDOWS_EXECUTION","observed_by":"LOCAL_CANARY"}}
        d.update(changes); d["canary_sha256"]=sha256_json(d); return d
    def test_valid_candidate(self): self.assertTrue(verify_real_local_candidate(self.evidence(),self.meta)["status"].startswith("E3_CANDIDATE"))
    def test_missing_installation(self):
        (self.root/".lidiya"/"installation.json").unlink()
        with self.assertRaises(ReconcileError): load_installation_metadata(self.root)
    def test_mismatched_installation(self):
        with self.assertRaises(ReconcileError): verify_real_local_candidate(self.evidence(installation_id="other"),self.meta)
    def test_wrong_auth(self):
        with self.assertRaises(ReconcileError): verify_real_local_candidate(self.evidence(authorization_ref="wrong"),self.meta)
    def test_hash_tamper(self):
        e=self.evidence(); e["stdout"]="tampered"
        with self.assertRaises(ReconcileError): verify_real_local_candidate(e,self.meta)
    def test_wrong_mode(self):
        with self.assertRaises(ReconcileError): verify_real_local_candidate(self.evidence(mode="ISOLATED_FAKE_EXECUTOR"),self.meta)
    def test_nonzero_exit(self):
        with self.assertRaises(ReconcileError): verify_real_local_candidate(self.evidence(exit_code=1),self.meta)
    def test_arbitrary_flag(self):
        with self.assertRaises(ReconcileError): verify_real_local_candidate(self.evidence(arbitrary_command_input=True),self.meta)
    def test_wrong_output(self):
        with self.assertRaises(ReconcileError): verify_real_local_candidate(self.evidence(stdout="OTHER\n"),self.meta)
if __name__=="__main__": unittest.main()
