import os
import tempfile
import unittest
from pathlib import Path

from metabolic_cleanup import CleanupRefused, apply, classify, manifest, plan


class MetabolicCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for directory in (
            "scratch",
            "workbench",
            "tmp",
            "state",
            "authorizations",
            "evidence",
        ):
            (self.root / directory).mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_classifies_disposable_and_hashes_without_contents(self):
        path = self.root / "scratch" / "debug.txt"
        path.write_text("waste", encoding="utf-8")
        decision = classify(self.root, path)
        self.assertEqual(decision.disposition, "DISPOSABLE")
        result = manifest([decision], mode="dry-run")
        self.assertFalse(result["content_values_retained"])
        self.assertEqual(decision.size, 5)
        self.assertEqual(len(decision.sha256 or ""), 64)
        self.assertTrue(path.exists())

    def test_apply_deletes_allowlisted_file(self):
        path = self.root / "tmp" / "x.txt"
        path.write_text("x", encoding="utf-8")
        decisions = plan(self.root, [path])
        apply(self.root, decisions)
        self.assertFalse(path.exists())

    def test_protected_state_not_deleted(self):
        path = self.root / "state" / "MISSION_STATE.json"
        path.write_text("{}", encoding="utf-8")
        decision = classify(self.root, path)
        self.assertEqual(decision.disposition, "PROTECTED")
        apply(self.root, [decision])
        self.assertTrue(path.exists())

    def test_evidence_outside_allowlist_is_retained(self):
        path = self.root / "evidence" / "result.json"
        path.write_text("{}", encoding="utf-8")
        decision = classify(self.root, path)
        self.assertEqual(decision.disposition, "RETAIN")
        apply(self.root, [decision])
        self.assertTrue(path.exists())

    def test_secret_like_path_is_protected_without_hashing(self):
        path = self.root / "scratch" / "api_key.txt"
        path.write_text("not-a-real-secret", encoding="utf-8")
        decision = classify(self.root, path)
        self.assertEqual(decision.disposition, "PROTECTED")
        self.assertIsNone(decision.sha256)
        self.assertIsNone(decision.size)
        apply(self.root, [decision])
        self.assertTrue(path.exists())

    def test_path_escape_refused(self):
        with self.assertRaises(CleanupRefused):
            classify(self.root, Path("../outside.txt"))

    @unittest.skipIf(not hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_escape_refused(self):
        outside = Path(self.temp.name).parent / "metabolic-outside-test"
        outside.mkdir(exist_ok=True)
        link = self.root / "scratch" / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
            with self.assertRaises(CleanupRefused):
                classify(self.root, link / "x.txt")
        finally:
            if link.exists() or link.is_symlink():
                link.unlink()
            try:
                outside.rmdir()
            except OSError:
                pass

    def test_nonempty_directory_fails_closed(self):
        directory = self.root / "scratch" / "dir"
        directory.mkdir()
        (directory / "x").write_text("x", encoding="utf-8")
        decision = classify(self.root, directory)
        with self.assertRaises(CleanupRefused):
            apply(self.root, [decision])


if __name__ == "__main__":
    unittest.main()
