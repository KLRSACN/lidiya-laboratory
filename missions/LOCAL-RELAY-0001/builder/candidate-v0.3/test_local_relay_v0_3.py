from __future__ import annotations
import hashlib,json,tempfile,threading,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from local_relay_dispatcher_v0_3 import *

def make_packet(token="TOKEN-1",task_id="TASK-1",attempt=0,max_attempts=3,target="ANY",text="hello",lease_seconds=10):
 p={"mission_id":"LOCAL-RELAY-0001","token":token,"task_id":task_id,"target_worker":target,"action":"WRITE_TEXT","objective":"write deterministic text","created_at":"2026-07-31T00:00:00Z","attempt":attempt,"max_attempts":max_attempts,"lease_seconds":lease_seconds,"payload":{"relative_output_path":f"outputs/{token}-{task_id}.txt","text":text},"success_criteria":["output exists"],"evidence_required":["sha256"],"lease_generation":0,"recovery_count":0}
 p["packet_sha256"]=packet_hash(p);return p

class Base(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/"runtime";self.d=LocalRelayDispatcher(self.root,[Path(self.tmp.name)])
 def tearDown(self):self.tmp.cleanup()

class Regression24(Base):
 def test_01_single_normal_task(self):
  self.d.enqueue(make_packet());r=self.d.scan_once("W1");self.assertEqual(r["status"],"COMPLETED");self.assertTrue((self.root/r["output_path"]).exists())
 def test_02_two_workers_atomic_claim(self):
  self.d.enqueue(make_packet(task_id="RACE"));bar=threading.Barrier(2);claims=[];lock=threading.Lock()
  def f(w):
   bar.wait();c=self.d.claim_next(w)
   with lock:claims.append(c)
  a=threading.Thread(target=f,args=("W1",));b=threading.Thread(target=f,args=("W2",));a.start();b.start();a.join();b.join();self.assertEqual(sum(x is not None for x in claims),1)
 def test_03_duplicate_completed(self):
  p=make_packet(task_id="DUP");self.d.enqueue(p);self.d.scan_once("W1");o=self.d.outbox_path(p);h=hashlib.sha256(o.read_bytes()).hexdigest();self.d.enqueue(p);self.assertEqual(self.d.scan_once("W2")["status"],"IDLE");self.assertEqual(h,hashlib.sha256(o.read_bytes()).hexdigest())
 def test_04_worker_crash(self):
  self.d.enqueue(make_packet(task_id="CRASH"));c=self.d.claim_next("W1");self.assertTrue(c.path.exists())
 def test_05_lease_expiry(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc);p=make_packet(task_id="EXP",lease_seconds=5);self.d.enqueue(p);self.d.claim_next("W1",t);self.assertEqual(self.d.recover_expired(t+timedelta(seconds=6))[0]["status"],"REQUEUED")
 def test_06_unexpired(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(make_packet(task_id="LIVE"));self.d.claim_next("W1",t);self.assertEqual(self.d.recover_expired(t+timedelta(seconds=3)),[])
 def test_07_heartbeat(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(make_packet(task_id="HB"));c=self.d.claim_next("W1",t);p=self.d.heartbeat(c,"W1",t+timedelta(seconds=8));self.assertEqual(p["lease"]["lease_expires_at"],"2026-01-01T00:00:18Z")
 def test_08_retry_limit(self):
  p=make_packet(task_id="LIMIT",attempt=1,max_attempts=2,text=None);p["packet_sha256"]=packet_hash(p);self.d.enqueue(p);self.assertEqual(self.d.scan_once("W1")["status"],"FAILED")
 def test_09_corrupt(self):
  (self.root/"inbox"/"bad.json").write_text("{bad");self.assertIsNone(self.d.claim_next("W1"));self.assertTrue(any((self.root/"quarantine").glob("bad*")))
 def test_10_missing(self):
  (self.root/"inbox"/"missing.json").write_text('{"mission_id":"x"}');self.assertIsNone(self.d.claim_next("W1"))
 def test_11_restart(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(make_packet(task_id="RESTART",lease_seconds=5));self.d.claim_next("W1",t);d2=LocalRelayDispatcher(self.root,[Path(self.tmp.name)]);self.assertEqual(d2.recover_expired(t+timedelta(seconds=6))[0]["status"],"REQUEUED")
 def test_12_partial_ignored(self):
  (self.root/"inbox"/".partial.json.tmp").write_text("{");self.assertIsNone(self.d.claim_next("W1"))
 def test_13_traversal(self):
  p=make_packet(task_id="TRAV");p["payload"]["relative_output_path"]="../escape";p["packet_sha256"]=packet_hash(p);self.d.enqueue(p);self.assertEqual(self.d.scan_once("W1")["status"],"FAILED")
 def test_14_outbox_persistence(self):
  p=make_packet(task_id="PERSIST");self.d.enqueue(p);self.d.scan_once("W1");d2=LocalRelayDispatcher(self.root,[Path(self.tmp.name)]);self.assertIsNotNone(d2.completed_record(p));self.assertTrue(d2.outbox_path(p).exists())
 def test_15_different_token(self):
  self.d.enqueue(make_packet(token="A",task_id="S"));self.d.enqueue(make_packet(token="B",task_id="S"));self.assertEqual([self.d.scan_once("W1")["status"],self.d.scan_once("W1")["status"]],["COMPLETED","COMPLETED"])
 def test_16_hash_mismatch(self):
  p=make_packet(task_id="HASH");p["packet_sha256"]="0"*64;(self.root/"inbox"/"hash.json").write_text(json.dumps(p));self.assertIsNone(self.d.claim_next("W1"))
 def test_17_action(self):
  p=make_packet(task_id="ACTION");p["action"]="SHELL";p["packet_sha256"]=packet_hash(p);(self.root/"inbox"/"action.json").write_text(json.dumps(p));self.assertIsNone(self.d.claim_next("W1"))
 def test_18_crash_outbox_registry(self):
  p=make_packet(task_id="GAP");self.d.enqueue(p);c=self.d.claim_next("W1")
  with self.assertRaises(FaultInjected):self.d.execute_claim(c,"W1",fault="after_outbox_before_registry")
  self.assertTrue(self.d.outbox_path(p).exists());self.assertIsNone(self.d.completed_record(p))
 def test_19_restart_outbox_only(self):
  p=make_packet(task_id="OR");self.d.enqueue(p);c=self.d.claim_next("W1")
  with self.assertRaises(FaultInjected):self.d.execute_claim(c,"W1",fault="after_outbox_before_registry")
  d2=LocalRelayDispatcher(self.root,[Path(self.tmp.name)]);self.assertIsNotNone(d2.completed_record(p))
 def test_20_registry_only(self):
  p=make_packet(task_id="RO");self.d.enqueue(p);self.d.scan_once("W1");self.d.outbox_path(p).unlink();LocalRelayDispatcher(self.root,[Path(self.tmp.name)]);self.assertTrue(self.d.outbox_path(p).exists())
 def test_21_stale_owner(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc);p=make_packet(task_id="STALE",lease_seconds=5);self.d.enqueue(p);old=self.d.claim_next("W1",t);self.d.recover_expired(t+timedelta(seconds=6));new=self.d.claim_next("W2",t+timedelta(seconds=6))
  with self.assertRaises(Invalid):self.d.execute_claim(old,"W1",t+timedelta(seconds=6))
  self.assertEqual(self.d.execute_claim(new,"W2",t+timedelta(seconds=6))["status"],"COMPLETED")
 def test_22_prepared_restart(self):
  p=make_packet(task_id="PREP");self.d.enqueue(p);c=self.d.claim_next("W1")
  with self.assertRaises(FaultInjected):self.d.execute_claim(c,"W1",fault="after_journal_before_outbox")
  LocalRelayDispatcher(self.root,[Path(self.tmp.name)]);self.assertTrue(self.d.outbox_path(p).exists())
 def test_23_conflict_blocked(self):
  p=make_packet(task_id="CONFLICT");self.d.enqueue(p);self.d.scan_once("W1");o=self.d.read_json(self.d.outbox_path(p));o["worker_id"]="EVIL";self.d.atomic_json_write(self.d.outbox_path(p),o);actions=self.d.reconcile();self.assertTrue(any(x["status"]=="BLOCKED" for x in actions))
 def test_24_root_constraint(self):
  with self.assertRaises(UnsafePath):self.d.atomic_json_write(self.root.parent/"escape.json",{})

class ProtocolV03(Base):
 def assert_invalid(self,p):
  p["packet_sha256"]=packet_hash(p)
  with self.assertRaises(Invalid):self.d.enqueue(p)
 def test_25_lease_min(self):self.assert_invalid(make_packet(lease_seconds=4))
 def test_26_lease_max(self):self.assert_invalid(make_packet(lease_seconds=3601))
 def test_27_empty_identity(self):
  p=make_packet();p["mission_id"]=" ";self.assert_invalid(p)
 def test_28_bad_created_at(self):
  p=make_packet();p["created_at"]="not-time";self.assert_invalid(p)
 def test_29_bad_target(self):
  p=make_packet(target="worker-one");self.assert_invalid(p)
 def test_30_runtime_allowlist(self):
  with self.assertRaises(Unsafe):LocalRelayDispatcher(Path(self.tmp.name)/"runtime",[Path(self.tmp.name)/"other"])
 def test_31_generation_increment(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc);p=make_packet(task_id="GEN",lease_seconds=5);self.d.enqueue(p);c1=self.d.claim_next("W1",t);self.assertEqual(c1.lease_generation,1);self.d.recover_expired(t+timedelta(seconds=6));c2=self.d.claim_next("W2",t+timedelta(seconds=6));self.assertEqual(c2.lease_generation,2)
 def test_32_generation_fencing(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc);p=make_packet(task_id="FENCE",lease_seconds=5);self.d.enqueue(p);old=self.d.claim_next("W1",t);self.d.recover_expired(t+timedelta(seconds=6));self.d.claim_next("W2",t+timedelta(seconds=6))
  with self.assertRaises(Invalid):self.d.submit_result(old,"W1",t+timedelta(seconds=6))
 def test_33_recovery_count(self):
  t=datetime(2026,1,1,tzinfo=timezone.utc);p=make_packet(task_id="RC",lease_seconds=5);self.d.enqueue(p);self.d.claim_next("W1",t);self.d.recover_expired(t+timedelta(seconds=6));q=self.d.read_json(next((self.root/"inbox").glob("*.json")));self.assertEqual(q["recovery_count"],1)
 def test_34_checkpoint_schema(self):
  p=make_packet(task_id="CP");self.d.enqueue(p);c=self.d.claim_next("W1");cp=self.d.read_checkpoint(c.path);self.assertEqual(cp["schema_version"],"LOCAL_RELAY_CHECKPOINT_V0.3");self.assertIn("lease_generation",cp);self.assertIn("pending_steps",cp)
 def test_35_state_schema(self):
  s=self.d.dispatcher_state();self.assertEqual(s["schema_version"],"LOCAL_RELAY_STATE_V0.3");self.assertIn("task_states",s);self.assertIn("authorized_runtime_roots",s)
 def test_36_registry_outbox_path(self):
  p=make_packet(task_id="OB");self.d.enqueue(p);self.d.scan_once("W1");r=self.d.completed_record(p);self.assertEqual(r["outbox_path"],str(self.d.outbox_path(p).relative_to(self.root)))

if __name__=="__main__":unittest.main(verbosity=2)
