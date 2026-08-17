import tempfile
import unittest
from pathlib import Path

from append_only_shadow_ledger import (
    AppendOnlyShadowLedger,
    LIVE_SHADOW_MODE,
    RESEARCH_MODE,
)


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

    def test_live_mode_without_trusted_anchor_fails_closed_before_append(self):
        with tempfile.TemporaryDirectory() as workspace:
            with self.assertRaisesRegex(ValueError, "LIVE_MODE_REQUIRES_TRUSTED_ANCHOR"):
                AppendOnlyShadowLedger(
                    Path(workspace),
                    mode=LIVE_SHADOW_MODE,
                    workspace_identity="install-1",
                )

    def test_live_mode_with_unbound_workspace_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as trusted:
            with self.assertRaisesRegex(ValueError, "LIVE_MODE_REQUIRES_BOUND_WORKSPACE_IDENTITY"):
                AppendOnlyShadowLedger(
                    Path(workspace),
                    mode=LIVE_SHADOW_MODE,
                    trusted_anchor_root=Path(trusted),
                )

    def test_research_unanchored_mode_is_explicitly_ineligible_for_promotion_evidence(self):
        with tempfile.TemporaryDirectory() as workspace:
            ledger = AppendOnlyShadowLedger(Path(workspace), mode=RESEARCH_MODE)
            rec = ledger.append(self._body("research-k1"))
            self.assertTrue(ledger.verify())
            self.assertFalse(ledger.promotion_evidence_status()["promotion_evidence_eligible"])
            self.assertFalse(rec["body"]["promotion_evidence_eligible"])
            self.assertEqual(rec["body"]["ledger_mode"], RESEARCH_MODE)

    def test_live_anchored_mode_marks_records_eligible_but_not_formal_pass(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as trusted:
            ledger = AppendOnlyShadowLedger(
                Path(workspace),
                mode=LIVE_SHADOW_MODE,
                workspace_identity="install-1",
                trusted_anchor_root=Path(trusted),
            )
            rec = ledger.append(self._body("live-k1"))
            status = ledger.promotion_evidence_status()
            self.assertTrue(ledger.verify())
            self.assertTrue(status["promotion_evidence_eligible"])
            self.assertFalse(status["formal_pass"])
            self.assertTrue(rec["body"]["promotion_evidence_eligible"])

    def test_paired_workspace_rollback_detected_by_external_anchor(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as trusted:
            ledger = AppendOnlyShadowLedger(
                Path(workspace),
                mode=LIVE_SHADOW_MODE,
                workspace_identity="install-1",
                trusted_anchor_root=Path(trusted),
            )
            ledger.append(self._body("k1"))
            old_ledger = ledger.path.read_text(encoding="utf-8")
            old_local_head = ledger.head_path.read_text(encoding="utf-8")
            ledger.append(self._body("k2"))
            self.assertTrue(ledger.verify())

            ledger.path.write_text(old_ledger, encoding="utf-8")
            ledger.head_path.write_text(old_local_head, encoding="utf-8")
            self.assertFalse(ledger.verify())

    def test_crash_ahead_or_anchor_rollback_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as trusted:
            ledger = AppendOnlyShadowLedger(
                Path(workspace),
                mode=LIVE_SHADOW_MODE,
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
                    mode=LIVE_SHADOW_MODE,
                    workspace_identity="install-1",
                    trusted_anchor_root=root / "local-anchor",
                )

    def test_workspace_identity_mismatch_cannot_reuse_anchor(self):
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as trusted:
            root = Path(workspace)
            source = AppendOnlyShadowLedger(
                root,
                mode=LIVE_SHADOW_MODE,
                workspace_identity="install-1",
                trusted_anchor_root=Path(trusted),
            )
            source.append(self._body("k1"))
            self.assertTrue(source.verify())

            mismatched = AppendOnlyShadowLedger(
                root,
                mode=LIVE_SHADOW_MODE,
                workspace_identity="install-2",
                trusted_anchor_root=Path(trusted),
            )
            self.assertFalse(mismatched.verify())


if __name__ == "__main__":
    unittest.main()
