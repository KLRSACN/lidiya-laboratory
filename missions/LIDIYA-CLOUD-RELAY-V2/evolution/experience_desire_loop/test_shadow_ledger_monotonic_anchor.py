import tempfile
import unittest
from pathlib import Path

from append_only_shadow_ledger import AppendOnlyShadowLedger


class ShadowLedgerMonotonicAnchorTests(unittest.TestCase):
    @staticmethod
    def _body(key: str) -> dict:
        return {
            "source_fingerprint": f"s-{key}",
            "origin_namespace": "DIRECT",
            "verifier_envelope_hash": "v",
            "schema_version": "1",
            "timestamp": "t",
            "dedupe_key": key,
        }

    def test_paired_workspace_rollback_detected_by_external_anchor(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as trusted:
            ledger = AppendOnlyShadowLedger(
                Path(workspace),
                workspace_identity="install-1",
                trusted_anchor_root=Path(trusted),
            )
            ledger.append(self._body("k1"))
            old_ledger = ledger.path.read_text(encoding="utf-8")
            old_local_head = ledger.head_path.read_text(encoding="utf-8")
            ledger.append(self._body("k2"))
            self.assertTrue(ledger.verify())

            # Roll back both files inside the workspace. The independently retained
            # trusted anchor remains at sequence 2 and must reject the old pair.
            ledger.path.write_text(old_ledger, encoding="utf-8")
            ledger.head_path.write_text(old_local_head, encoding="utf-8")
            self.assertFalse(ledger.verify())

    def test_crash_ahead_or_anchor_rollback_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as trusted:
            ledger = AppendOnlyShadowLedger(
                Path(workspace),
                workspace_identity="install-1",
                trusted_anchor_root=Path(trusted),
            )
            ledger.append(self._body("k1"))
            old_anchor = ledger.trusted_anchor_path.read_text(encoding="utf-8")
            ledger.append(self._body("k2"))
            ledger.trusted_anchor_path.write_text(old_anchor, encoding="utf-8")
            self.assertFalse(ledger.verify())

    def test_trusted_anchor_cannot_be_inside_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            with self.assertRaisesRegex(ValueError, "TRUSTED_ANCHOR_INSIDE_WORKSPACE"):
                AppendOnlyShadowLedger(
                    root,
                    workspace_identity="install-1",
                    trusted_anchor_root=root / "local-anchor",
                )

    def test_workspace_identity_mismatch_cannot_reuse_anchor(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as trusted:
            root = Path(workspace)
            source = AppendOnlyShadowLedger(
                root,
                workspace_identity="install-1",
                trusted_anchor_root=Path(trusted),
            )
            source.append(self._body("k1"))
            self.assertTrue(source.verify())

            mismatched = AppendOnlyShadowLedger(
                root,
                workspace_identity="install-2",
                trusted_anchor_root=Path(trusted),
            )
            self.assertFalse(mismatched.verify())


if __name__ == "__main__":
    unittest.main()
