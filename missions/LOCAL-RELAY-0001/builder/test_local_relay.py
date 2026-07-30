from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from local_relay_dispatcher import LocalRelayDispatcher, UnsafePath, packet_hash


def make_packet(token="TOKEN-1", task_id="TASK-1", attempt=0, max_attempts=3, target="ANY", text="hello"):
    packet = {
        "mission_id": "LOCAL-RELAY-0001",
        "token": token,
        "task_id": task_id,
        "target_worker": target,
        "action": "WRITE_TEXT",
        "objective": "write deterministic text",
        "created_at": "2026-07-31T00:00:00Z",
        "attempt": attempt,
        "max_attempts": max_attempts,
        "lease_seconds": 10,
        "payload": {"relative_output_path": f"outputs/{token}-{task_id}.txt", "text": text},
        "success_criteria": ["output exists"],
        "evidence_required": ["sha256"],
    }
    packet["packet_sha256"] = packet_hash(packet)
    return packet


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "runtime"
        self.d = LocalRelayDispatcher(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_01_single_normal_task(self):
        self.d.enqueue(make_packet())
        result = self.d.scan_once("W1")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertTrue((self.root / result["output_path"]).exists())

    def test_02_two_workers_atomic_claim(self):
        self.d.enqueue(make_packet(task_id="RACE"))
        barrier = threading.Barrier(2)
        claims = []
        lock = threading.Lock()
        def run(worker):
            barrier.wait()
            claim = self.d.claim_next(worker)
            with lock:
                claims.append(claim)
        t1 = threading.Thread(target=run, args=("W1",)); t2 = threading.Thread(target=run, args=("W2",))
        t1.start(); t2.start(); t1.join(); t2.join()
        self.assertEqual(sum(c is not None for c in claims), 1)

    def test_03_duplicate_completed(self):
        p = make_packet(task_id="DUP")
        self.d.enqueue(p); first = self.d.scan_once("W1")
        out = self.root / "outbox" / "LOCAL-RELAY-0001__TOKEN-1__DUP.result.json"
        before = hashlib.sha256(out.read_bytes()).hexdigest()
        self.d.enqueue(p); second = self.d.scan_once("W2")
        after = hashlib.sha256(out.read_bytes()).hexdigest()
        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(second["status"], "IDLE")
        self.assertEqual(before, after)

    def test_04_worker_crash_leaves_running(self):
        self.d.enqueue(make_packet(task_id="CRASH"))
        claim = self.d.claim_next("W1")
        self.assertIsNotNone(claim)
        self.assertTrue(claim.path.exists())
        self.assertEqual(len(list((self.root / "outbox").glob("*.json"))), 0)

    def test_05_lease_expiry_recovery(self):
        p = make_packet(task_id="EXP"); p["lease_seconds"] = 1; p["packet_sha256"] = packet_hash(p)
        self.d.enqueue(p); self.d.claim_next("W1", datetime(2026,1,1,tzinfo=timezone.utc))
        rec = self.d.recover_expired(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=2))
        self.assertEqual(rec[0]["status"], "REQUEUED")

    def test_06_unexpired_lease_not_recovered(self):
        p = make_packet(task_id="LIVE"); self.d.enqueue(p)
        self.d.claim_next("W1", datetime(2026,1,1,tzinfo=timezone.utc))
        rec = self.d.recover_expired(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=5))
        self.assertEqual(rec, [])

    def test_07_heartbeat_extends_lease(self):
        p = make_packet(task_id="HB"); self.d.enqueue(p)
        claim = self.d.claim_next("W1", datetime(2026,1,1,tzinfo=timezone.utc))
        updated = self.d.heartbeat(claim.path, "W1", datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=8))
        self.assertEqual(updated["lease"]["lease_expires_at"], "2026-01-01T00:00:18Z")

    def test_08_retry_limit(self):
        p = make_packet(task_id="LIMIT", attempt=1, max_attempts=2); p["payload"]["text"] = None; p["packet_sha256"] = packet_hash(p)
        self.d.enqueue(p); result = self.d.scan_once("W1")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(list((self.root / "failed").glob("*.json"))), 1)

    def test_09_corrupt_json_quarantine(self):
        (self.root / "inbox" / "bad.json").write_text("{bad", encoding="utf-8")
        self.assertIsNone(self.d.claim_next("W1"))
        self.assertTrue((self.root / "quarantine" / "bad.__owner__W1.json").exists())

    def test_10_missing_field_quarantine(self):
        (self.root / "inbox" / "missing.json").write_text(json.dumps({"mission_id":"x"}), encoding="utf-8")
        self.assertIsNone(self.d.claim_next("W1"))
        self.assertTrue(any((self.root / "quarantine").glob("missing*")))

    def test_11_restart_recovery(self):
        p = make_packet(task_id="RESTART"); p["lease_seconds"] = 1; p["packet_sha256"] = packet_hash(p)
        self.d.enqueue(p); self.d.claim_next("W1", datetime(2026,1,1,tzinfo=timezone.utc))
        d2 = LocalRelayDispatcher(self.root)
        rec = d2.recover_expired(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=2))
        self.assertEqual(rec[0]["status"], "REQUEUED")

    def test_12_partial_temp_file_ignored(self):
        (self.root / "inbox" / ".partial.json.tmp").write_text("{", encoding="utf-8")
        self.assertIsNone(self.d.claim_next("W1"))
        self.assertTrue((self.root / "inbox" / ".partial.json.tmp").exists())

    def test_13_path_traversal_rejected(self):
        p = make_packet(task_id="TRAV"); p["payload"]["relative_output_path"] = "../escape.txt"; p["packet_sha256"] = packet_hash(p)
        self.d.enqueue(p); result = self.d.scan_once("W1")
        self.assertEqual(result["status"], "FAILED")
        self.assertFalse((self.root.parent / "escape.txt").exists())
        with self.assertRaises(UnsafePath): self.d.safe_path("..", "escape")

    def test_14_outbox_persistence(self):
        p = make_packet(task_id="PERSIST"); self.d.enqueue(p); self.d.scan_once("W1")
        d2 = LocalRelayDispatcher(self.root)
        self.assertIsNotNone(d2.completed_record(p))
        self.assertTrue(d2._outbox_result_path(p).exists())

    def test_15_different_token_independent(self):
        self.d.enqueue(make_packet(token="A", task_id="SAME")); self.d.enqueue(make_packet(token="B", task_id="SAME"))
        r1 = self.d.scan_once("W1"); r2 = self.d.scan_once("W1")
        self.assertEqual([r1["status"], r2["status"]], ["COMPLETED", "COMPLETED"])

    def test_16_hash_mismatch_quarantine(self):
        p = make_packet(task_id="HASH"); p["packet_sha256"] = "0"*64
        (self.root / "inbox" / "hash.json").write_text(json.dumps(p), encoding="utf-8")
        self.assertIsNone(self.d.claim_next("W1"))
        self.assertTrue(any((self.root / "quarantine").glob("hash*")))

    def test_17_unsupported_action_quarantine(self):
        p = make_packet(task_id="ACTION"); p["action"] = "SHELL"; p["packet_sha256"] = packet_hash(p)
        (self.root / "inbox" / "action.json").write_text(json.dumps(p), encoding="utf-8")
        self.assertIsNone(self.d.claim_next("W1"))
        self.assertTrue(any((self.root / "quarantine").glob("action*")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
