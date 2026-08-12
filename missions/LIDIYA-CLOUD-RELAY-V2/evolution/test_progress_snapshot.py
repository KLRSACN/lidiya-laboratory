import tempfile
import unittest
from pathlib import Path

from progress_snapshot import ProgressGuardError, normalize_snapshot, write_progress_snapshot

def snapshot(saved_at="2026-08-12T10:40:00+08:00", step_id=1):
    return {"schema_version":"1.0","mission_id":"LCR-EVOLUTION-0005","saved_at":saved_at,"mission_status":"READY_FOR_BUILDER","current_role":"LCR-B","step_id":step_id,"verified_evidence":[],"blocker":None,"storage_ledger":{},"package_radar_delta":{},"evolution_suggestions":[],"self_review":{},"next_autonomous_action":{}}

class ProgressTests(unittest.TestCase):
    def test_same_input_deterministic(self): self.assertEqual(normalize_snapshot(snapshot()), normalize_snapshot(snapshot()))
    def test_missing_required_field_rejected(self):
        s=snapshot(); s.pop("self_review")
        with self.assertRaises(ProgressGuardError): normalize_snapshot(s)
    def test_only_canonical_progress_path_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProgressGuardError): write_progress_snapshot(Path(tmp)/"state"/"progress-001.json",snapshot())
    def test_write_overwrites_single_canonical_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state"/"EVOLUTION_PROGRESS.json"
            first=write_progress_snapshot(path,snapshot()); second=write_progress_snapshot(path,snapshot("2026-08-12T10:41:00+08:00"))
            self.assertTrue(path.exists()); self.assertNotEqual(first["snapshot_sha256"],second["snapshot_sha256"]); self.assertEqual(len(list(path.parent.glob("EVOLUTION_PROGRESS*.json"))),1)
    def test_stale_step_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state"/"EVOLUTION_PROGRESS.json"; write_progress_snapshot(path,snapshot(step_id=2))
            with self.assertRaises(ProgressGuardError): write_progress_snapshot(path,snapshot(step_id=1))
    def test_stale_timestamp_same_step_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"state"/"EVOLUTION_PROGRESS.json"; write_progress_snapshot(path,snapshot("2026-08-12T10:42:00+08:00"))
            with self.assertRaises(ProgressGuardError): write_progress_snapshot(path,snapshot("2026-08-12T10:41:00+08:00"))

if __name__ == "__main__": unittest.main()
