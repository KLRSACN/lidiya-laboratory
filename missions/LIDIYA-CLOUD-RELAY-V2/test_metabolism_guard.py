from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from metabolism_guard import (
    Artifact,
    GuardRejected,
    cleanup_fixture,
    classify,
    validate_backup_groups,
)


class BackupPolicyTests(unittest.TestCase):
    def test_two_authorized_backups_are_valid(self):
        validate_backup_groups({
            "RECOVERY_BASELINE": "READ_ONLY",
            "WORKING_EXCHANGE": "MUTABLE_COLLABORATION",
        })

    def test_third_backup_is_rejected(self):
        with self.assertRaises(GuardRejected):
            validate_backup_groups({
                "RECOVERY_BASELINE": "READ_ONLY",
                "WORKING_EXCHANGE": "MUTABLE_COLLABORATION",
                "EXTRA_COPY": "MUTABLE_COLLABORATION",
            })

    def test_recovery_baseline_cannot_be_mutable(self):
        with self.assertRaises(GuardRejected):
            validate_backup_groups({
                "RECOVERY_BASELINE": "MUTABLE_COLLABORATION",
                "WORKING_EXCHANGE": "MUTABLE_COLLABORATION",
            })


class ClassificationTests(unittest.TestCase):
    def test_referenced_artifact_is_kept(self):
        decision = classify(Artifact(
            "scratch/referenced.tmp",
            "stage_scratch",
            referenced=True,
            reproducible=True,
            recovery_ok=True,
        ))
        self.assertEqual(decision.disposition, "KEEP")
        self.assertFalse(decision.guards.reachability)

    def test_unique_artifact_is_kept(self):
        decision = classify(Artifact(
            "scratch/unique.tmp",
            "stage_scratch",
            unique=True,
            reproducible=True,
            recovery_ok=True,
        ))
        self.assertEqual(decision.disposition, "KEEP")
        self.assertFalse(decision.guards.uniqueness)

    def test_unreproducible_artifact_is_quarantined(self):
        decision = classify(Artifact(
            "scratch/unreproducible.tmp",
            "stage_scratch",
            reproducible=False,
            recovery_ok=True,
        ))
        self.assertEqual(decision.disposition, "QUARANTINE")
        self.assertFalse(decision.guards.reproducibility)

    def test_recovery_failure_is_quarantined(self):
        decision = classify(Artifact(
            "scratch/no-recovery.tmp",
            "stage_scratch",
            reproducible=True,
            recovery_ok=False,
        ))
        self.assertEqual(decision.disposition, "QUARANTINE")
        self.assertFalse(decision.guards.recovery)

    def test_secret_like_path_is_quarantined(self):
        decision = classify(Artifact(
            "scratch/api_token.tmp",
            "stage_scratch",
            reproducible=True,
            recovery_ok=True,
        ))
        self.assertEqual(decision.disposition, "QUARANTINE")

    def test_protected_recovery_path_is_kept(self):
        decision = classify(Artifact(
            "recovery_baseline/core.snapshot",
            "stage_scratch",
            reproducible=True,
            recovery_ok=True,
        ))
        self.assertEqual(decision.disposition, "KEEP")

    def test_safe_stage_garbage_becomes_delete_candidate(self):
        decision = classify(Artifact(
            "scratch/safe.tmp",
            "stage_scratch",
            reproducible=True,
            recovery_ok=True,
        ))
        self.assertEqual(decision.disposition, "DELETE_CANDIDATE")
        self.assertTrue(decision.guards.all_pass)


class FixtureCleanupTests(unittest.TestCase):
    def test_apply_deletes_only_safe_fixture_and_retains_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scratch").mkdir()
            safe = root / "scratch" / "safe.tmp"
            safe.write_text("disposable", encoding="utf-8")
            protected = root / "scratch" / "unique.tmp"
            protected.write_text("human-value", encoding="utf-8")

            artifacts = [
                Artifact(
                    "scratch/safe.tmp",
                    "stage_scratch",
                    reproducible=True,
                    recovery_ok=True,
                ),
                Artifact(
                    "scratch/unique.tmp",
                    "stage_scratch",
                    unique=True,
                    reproducible=True,
                    recovery_ok=True,
                ),
            ]
            report = cleanup_fixture(root, artifacts, apply=True)
            self.assertFalse(safe.exists())
            self.assertTrue(protected.exists())
            self.assertEqual(report["deleted"], ["scratch/safe.tmp"])
            self.assertEqual(report["deleted_count"], 1)
            self.assertEqual(report["reclaimed_bytes"], len("disposable"))
            self.assertEqual(report["dispositions"]["KEEP"], 1)
            self.assertEqual(report["dispositions"]["DELETE_CANDIDATE"], 1)
            self.assertFalse(report["raw_worksite_retained"])

    def test_dry_run_is_deterministic_and_does_not_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scratch").mkdir()
            target = root / "scratch" / "safe.tmp"
            target.write_text("disposable", encoding="utf-8")
            artifacts = [Artifact(
                "scratch/safe.tmp",
                "stage_scratch",
                reproducible=True,
                recovery_ok=True,
            )]
            first = cleanup_fixture(root, artifacts, apply=False)
            second = cleanup_fixture(root, artifacts, apply=False)
            self.assertTrue(target.exists())
            self.assertEqual(first["before_manifest_sha256"], second["before_manifest_sha256"])
            self.assertEqual(first["after_manifest_sha256"], second["after_manifest_sha256"])
            self.assertEqual(first["report_sha256"], second["report_sha256"])

    def test_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(GuardRejected):
                cleanup_fixture(
                    Path(tmp),
                    [Artifact("../escape.tmp", "stage_scratch", reproducible=True, recovery_ok=True)],
                    apply=False,
                )


if __name__ == "__main__":
    unittest.main()
