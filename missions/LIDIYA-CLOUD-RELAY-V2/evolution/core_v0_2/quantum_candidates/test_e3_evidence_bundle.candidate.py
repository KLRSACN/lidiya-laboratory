import copy, unittest, uuid
from e3_evidence_bundle import validate_bundle, sha256_json, E3BundleError, AUTH_REF, PROMOTION, REQUIRED_FILES

class E3BundleTests(unittest.TestCase):
    def base(self):
        inst={"schema_version":"1.0","installation_id":str(uuid.uuid4()),"install_root":"C:/Lidiya","created_at":"2026-08-15T01:00:00Z","component":"LIDIYA-LOCAL-NAV-COMMAND-TOWER-TYPE-1","transport":"LOOPBACK_AND_WORKSPACE_SPOOL","privilege":"USER_SPACE"}
        can={"mode":"WINDOWS_FIXED_HARMLESS_ECHO","command_id":"LOCAL-CANARY-ECHO-001","stdout":"LIDIYA_CANARY\n","stderr":"","exit_code":0,"evidence_sha256":"a"*64,"authorization_ref":AUTH_REF,"arbitrary_command_input":False,"installation_id":inst["installation_id"],"installation_fingerprint":sha256_json(inst),"install_root":"C:/Lidiya","provenance":{"source":"LOCAL_OWNER_WINDOWS_EXECUTION","observed_by":"LOCAL_CANARY"},"promotion_status":"REAL_LOCAL_CANARY_EVIDENCE_CANDIDATE_UNATTESTED"}
        can["canary_sha256"]=sha256_json(can)
        return {"schema_version":"1.0","mission_id":"LCR-EVOLUTION-0005","authorization_ref":AUTH_REF,"capture_mode":"OWNER_WINDOWS_LOCAL_PACKAGE","installation":inst,"canary":can,"health":{"host":"127.0.0.1","port":8765,"observed":True},"package_files":{p:"b"*64 for p in REQUIRED_FILES},"promotion_status":PROMOTION,"E3_promoted":False}
    def assertReject(self,b):
        with self.assertRaises((E3BundleError,ValueError,TypeError)): validate_bundle(b)
    def test_valid_candidate_never_promotes(self):
        out=validate_bundle(self.base()); self.assertFalse(out["E3_promoted"]); self.assertFalse(out["online_source_attested"])
    def test_wrong_auth_rejected(self):
        b=self.base(); b["authorization_ref"]="wrong"; self.assertReject(b)
    def test_arbitrary_command_rejected(self):
        b=self.base(); b["canary"]["arbitrary_command_input"]=True; b["canary"]["canary_sha256"]=sha256_json({k:v for k,v in b["canary"].items() if k!="canary_sha256"}); self.assertReject(b)
    def test_tampered_canary_hash_rejected(self):
        b=self.base(); b["canary"]["stdout"]="tampered"; self.assertReject(b)
    def test_wrong_root_rejected(self):
        b=self.base(); b["canary"]["install_root"]="C:/Other"; b["canary"]["canary_sha256"]=sha256_json({k:v for k,v in b["canary"].items() if k!="canary_sha256"}); self.assertReject(b)
    def test_public_health_rejected(self):
        b=self.base(); b["health"]["host"]="0.0.0.0"; self.assertReject(b)
    def test_missing_required_package_rejected(self):
        b=self.base(); b["package_files"].pop(next(iter(REQUIRED_FILES))); self.assertReject(b)
    def test_path_escape_rejected(self):
        b=self.base(); b["package_files"]["../escape.txt"]="c"*64; self.assertReject(b)
    def test_bad_digest_rejected(self):
        b=self.base(); b["package_files"][next(iter(REQUIRED_FILES))]="bad"; self.assertReject(b)
    def test_premature_e3_rejected(self):
        b=self.base(); b["E3_promoted"]=True; self.assertReject(b)
    def test_wrong_fixed_command_rejected(self):
        b=self.base(); b["canary"]["command_id"]="ARBITRARY"; b["canary"]["canary_sha256"]=sha256_json({k:v for k,v in b["canary"].items() if k!="canary_sha256"}); self.assertReject(b)

if __name__=="__main__": unittest.main()
