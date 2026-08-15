import hashlib
import tempfile
import unittest
import uuid
from pathlib import Path

from e3_evidence_bundle import (
    AUTH_REF,
    E3BundleError,
    PROMOTION,
    REQUIRED_FILES,
    sha256_json,
    validate_bundle,
)


TRUST_ANCHORS = (
    "evolution/small_nest/PREPARE_E3_OWNER_RUN.ps1",
    "evolution/small_nest/E3_OWNER_RUN_CONTRACT.json",
    "evolution/local_command_tower/e3_evidence_bundle.py",
)


class E3BundleTests(unittest.TestCase):
    def base(self, install_root="C:/Lidiya"):
        inst = {
            "schema_version": "1.0",
            "installation_id": str(uuid.uuid4()),
            "install_root": install_root,
            "created_at": "2026-08-15T01:00:00Z",
            "component": "LIDIYA-LOCAL-NAV-COMMAND-TOWER-TYPE-1",
            "transport": "LOOPBACK_AND_WORKSPACE_SPOOL",
            "privilege": "USER_SPACE",
        }
        can = {
            "mode": "WINDOWS_FIXED_HARMLESS_ECHO",
            "command_id": "LOCAL-CANARY-ECHO-001",
            "stdout": "LIDIYA_CANARY\n",
            "stderr": "",
            "exit_code": 0,
            "evidence_sha256": "a" * 64,
            "authorization_ref": AUTH_REF,
            "arbitrary_command_input": False,
            "installation_id": inst["installation_id"],
            "installation_fingerprint": sha256_json(inst),
            "install_root": install_root,
            "provenance": {"source": "LOCAL_OWNER_WINDOWS_EXECUTION", "observed_by": "LOCAL_CANARY"},
            "promotion_status": "REAL_LOCAL_CANARY_EVIDENCE_CANDIDATE_UNATTESTED",
        }
        can["canary_sha256"] = sha256_json(can)
        return {
            "schema_version": "1.0",
            "mission_id": "LCR-EVOLUTION-0005",
            "authorization_ref": AUTH_REF,
            "capture_mode": "OWNER_WINDOWS_LOCAL_PACKAGE",
            "installation": inst,
            "canary": can,
            "health": {"host": "127.0.0.1", "port": 8765, "observed": True},
            "package_files": {p: "b" * 64 for p in REQUIRED_FILES},
            "promotion_status": PROMOTION,
            "E3_promoted": False,
        }

    def rehash_canary(self, b):
        b["canary"]["canary_sha256"] = sha256_json({k: v for k, v in b["canary"].items() if k != "canary_sha256"})

    def assertReject(self, b, **kwargs):
        with self.assertRaises((E3BundleError, ValueError, TypeError)):
            validate_bundle(b, **kwargs)

    def make_workspace_bundle(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name).resolve()
        b = self.base(str(root))
        for rel in REQUIRED_FILES:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(rel, encoding="utf-8")
            b["package_files"][rel] = hashlib.sha256(rel.encode("utf-8")).hexdigest()
        b["installation"]["install_root"] = str(root)
        b["canary"]["install_root"] = str(root)
        b["canary"]["installation_fingerprint"] = sha256_json(b["installation"])
        self.rehash_canary(b)
        return td, root, b

    def test_valid_candidate_never_promotes(self):
        out = validate_bundle(self.base())
        self.assertEqual(out["status"], PROMOTION)
        self.assertFalse(out["E3_promoted"])
        self.assertFalse(out["online_source_attested"])

    def test_wrong_auth_rejected(self):
        b = self.base(); b["authorization_ref"] = "wrong"; self.assertReject(b)

    def test_wrong_mission_rejected(self):
        b = self.base(); b["mission_id"] = "wrong"; self.assertReject(b)

    def test_wrong_mode_rejected(self):
        b = self.base(); b["canary"]["mode"] = "OTHER"; self.rehash_canary(b); self.assertReject(b)

    def test_arbitrary_command_rejected(self):
        b = self.base(); b["canary"]["arbitrary_command_input"] = True; self.rehash_canary(b); self.assertReject(b)

    def test_tampered_canary_hash_rejected(self):
        b = self.base(); b["canary"]["stdout"] = "tampered"; self.assertReject(b)

    def test_wrong_stdout_rejected(self):
        b = self.base(); b["canary"]["stdout"] = "NOT_CANARY"; self.rehash_canary(b); self.assertReject(b)

    def test_nonzero_exit_rejected(self):
        b = self.base(); b["canary"]["exit_code"] = 1; self.rehash_canary(b); self.assertReject(b)

    def test_wrong_root_rejected(self):
        b = self.base(); b["canary"]["install_root"] = "C:/Other"; self.rehash_canary(b); self.assertReject(b)

    def test_public_health_rejected(self):
        b = self.base(); b["health"]["host"] = "0.0.0.0"; self.assertReject(b)

    def test_missing_required_package_rejected(self):
        b = self.base(); b["package_files"].pop(next(iter(REQUIRED_FILES))); self.assertReject(b)

    def test_extra_package_rejected(self):
        b = self.base(); b["package_files"]["extra.txt"] = "c" * 64; self.assertReject(b)

    def test_bad_digest_rejected(self):
        b = self.base(); b["package_files"][next(iter(REQUIRED_FILES))] = "bad"; self.assertReject(b)

    def test_premature_e3_rejected(self):
        b = self.base(); b["E3_promoted"] = True; self.assertReject(b)

    def test_wrong_fixed_command_rejected(self):
        b = self.base(); b["canary"]["command_id"] = "ARBITRARY"; self.rehash_canary(b); self.assertReject(b)

    def test_wrong_provenance_rejected(self):
        b = self.base(); b["canary"]["provenance"]["source"] = "ONLINE"; self.rehash_canary(b); self.assertReject(b)

    def test_installation_fingerprint_mismatch_rejected(self):
        b = self.base(); b["canary"]["installation_fingerprint"] = "0" * 64; self.rehash_canary(b); self.assertReject(b)

    def test_workspace_file_digest_verified(self):
        td, root, b = self.make_workspace_bundle()
        try:
            out = validate_bundle(b, workspace_root=root)
            self.assertFalse(out["E3_promoted"])
        finally:
            td.cleanup()

    def test_workspace_file_tamper_rejected(self):
        td, root, b = self.make_workspace_bundle()
        try:
            (root / next(iter(REQUIRED_FILES))).write_text("tampered", encoding="utf-8")
            self.assertReject(b, workspace_root=root)
        finally:
            td.cleanup()

    def test_prepare_script_trust_anchor_tamper_rejected(self):
        td, root, b = self.make_workspace_bundle()
        try:
            (root / TRUST_ANCHORS[0]).write_text("tampered-prepare", encoding="utf-8")
            self.assertReject(b, workspace_root=root)
        finally:
            td.cleanup()

    def test_owner_run_contract_trust_anchor_tamper_rejected(self):
        td, root, b = self.make_workspace_bundle()
        try:
            (root / TRUST_ANCHORS[1]).write_text("tampered-contract", encoding="utf-8")
            self.assertReject(b, workspace_root=root)
        finally:
            td.cleanup()

    def test_bundle_validator_trust_anchor_tamper_rejected(self):
        td, root, b = self.make_workspace_bundle()
        try:
            (root / TRUST_ANCHORS[2]).write_text("tampered-validator", encoding="utf-8")
            self.assertReject(b, workspace_root=root)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
