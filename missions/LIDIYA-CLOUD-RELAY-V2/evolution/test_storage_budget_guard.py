import unittest

from storage_budget_guard import StorageGuardError, evaluate_write, validate_backup_groups, validate_base_weight_admission

class StorageTests(unittest.TestCase):
    def test_normal_write_allowed(self): self.assertTrue(evaluate_write(known_used_bytes=0,reserved_bytes=0,proposed_size_bytes=100).allow_write)
    def test_70_percent_compaction(self): self.assertEqual(evaluate_write(known_used_bytes=699_999_999_999,reserved_bytes=0,proposed_size_bytes=1).action,"ALLOW_WITH_COMPACTION")
    def test_85_percent_stops_large_checkpoint(self):
        d=evaluate_write(known_used_bytes=850_000_000_000,reserved_bytes=0,proposed_size_bytes=0,large_write=True); self.assertFalse(d.allow_write); self.assertEqual(d.action,"STOP_NEW_LARGE_CHECKPOINT")
    def test_95_percent_large_write_human_gate(self):
        d=evaluate_write(known_used_bytes=950_000_000_000,reserved_bytes=0,proposed_size_bytes=0,large_write=True); self.assertFalse(d.allow_write); self.assertTrue(d.human_gate)
    def test_100_percent_rejected(self): self.assertEqual(evaluate_write(known_used_bytes=999_999_999_999,reserved_bytes=0,proposed_size_bytes=1).action,"HARD_REJECT")
    def test_above_ceiling_rejected(self): self.assertFalse(evaluate_write(known_used_bytes=999_999_999_999,reserved_bytes=0,proposed_size_bytes=2).allow_write)
    def test_unknown_large_size_rejected_before_write(self):
        with self.assertRaises(StorageGuardError): evaluate_write(known_used_bytes=1,reserved_bytes=0,proposed_size_bytes=None,large_write=True)
    def test_third_backup_rejected(self):
        with self.assertRaises(StorageGuardError): validate_backup_groups(["RECOVERY_BASELINE","WORKING_EXCHANGE","EXTRA"])
    def test_two_backups_allowed(self): validate_backup_groups(["RECOVERY_BASELINE","WORKING_EXCHANGE"])
    def test_duplicate_base_requires_format_and_manifest_reason(self):
        h="a"*64
        with self.assertRaises(StorageGuardError): validate_base_weight_admission(content_sha256=h,existing_hashes=[h],required_format=None,manifested_reason=None)
        validate_base_weight_admission(content_sha256=h,existing_hashes=[h],required_format="GGUF",manifested_reason="required runtime format")
    def test_new_base_requires_content_hash(self):
        with self.assertRaises(StorageGuardError): validate_base_weight_admission(content_sha256="bad",existing_hashes=[],required_format=None,manifested_reason=None)

if __name__ == "__main__": unittest.main()
