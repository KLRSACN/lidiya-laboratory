import unittest,tempfile,threading,json,hashlib,os
from pathlib import Path
from datetime import datetime,timedelta,timezone
from local_relay_dispatcher_v0_3 import *
from relay_auditor_adapter_v0_3 import AuditorAdapter

def packet(task='T1',token='TOK',target='ANY',lease=10,text='hello',attempt=0,max_attempts=3):
 p={'schema_version':'LOCAL_RELAY_TASK_V0.3','mission_id':'LOCAL-RELAY-0001','token':token,'task_id':task,'target_worker':target,'action':'WRITE_TEXT','objective':'write text','created_at':'2026-08-01T00:00:00Z','attempt':attempt,'max_attempts':max_attempts,'lease_seconds':lease,'payload':{'relative_output_path':f'outputs/{token}-{task}.txt','text':text},'success_criteria':['output exists'],'evidence_required':['sha256'],'lease_generation':0,'recovery_count':0};p['packet_sha256']=packet_hash(p);return p
class B(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.base=Path(self.t.name);self.root=self.base/'runtime';self.d=LocalRelayDispatcher(self.root,[self.base]);self.a=AuditorAdapter(self.d)
 def tearDown(self):self.t.cleanup()
 def bad(self,p):p['packet_sha256']=packet_hash(p);self.assertRaises(Invalid,self.d.enqueue,p)
class Tests(B):
 def test_01_normal(self):self.d.enqueue(packet());self.assertEqual(self.d.scan_once('W1')['status'],'COMPLETED')
 def test_02_atomic_claim(self):
  self.d.enqueue(packet('R'));bar=threading.Barrier(2);x=[]
  def f(w):bar.wait();x.append(self.d.claim(w))
  a=threading.Thread(target=f,args=('W1',));b=threading.Thread(target=f,args=('W2',));a.start();b.start();a.join();b.join();self.assertEqual(sum(v is not None for v in x),1)
 def test_03_duplicate(self):p=packet('D');self.d.enqueue(p);self.d.scan_once('W1');h=hashlib.sha256(self.d.outbox_path(p).read_bytes()).hexdigest();self.d.enqueue(p);self.assertEqual(self.d.scan_once('W2')['status'],'IDLE');self.assertEqual(h,hashlib.sha256(self.d.outbox_path(p).read_bytes()).hexdigest())
 def test_04_crash_running(self):self.d.enqueue(packet('C'));self.assertTrue(self.d.claim('W1').path.exists())
 def test_05_expiry(self):t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(packet('E',lease=5));self.d.claim('W1',t);self.assertEqual(self.d.recover(t+timedelta(seconds=6))[0]['status'],'REQUEUED')
 def test_06_unexpired(self):t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(packet('U'));self.d.claim('W1',t);self.assertEqual(self.d.recover(t+timedelta(seconds=2)),[])
 def test_07_heartbeat(self):t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(packet('H'));c=self.d.claim('W1',t);self.assertIn('lease_expires_at',self.d.heartbeat(c,'W1',c.lease_generation,t+timedelta(seconds=1))['lease'])
 def test_08_retry_limit(self):p=packet('L',text=None,attempt=1,max_attempts=2);p['packet_sha256']=packet_hash(p);self.d.enqueue(p);self.assertEqual(self.d.scan_once('W1')['status'],'FAILED')
 def test_09_corrupt(self):(self.root/'inbox'/'bad.json').write_text('{');self.assertIsNone(self.d.claim('W1'))
 def test_10_missing(self):(self.root/'inbox'/'m.json').write_text('{}');self.assertIsNone(self.d.claim('W1'))
 def test_11_restart(self):t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(packet('RS',lease=5));self.d.claim('W1',t);d2=LocalRelayDispatcher(self.root,[self.base]);self.assertEqual(d2.recover(t+timedelta(seconds=6))[0]['status'],'REQUEUED')
 def test_12_partial(self):(self.root/'inbox'/'.x.tmp').write_text('{');self.assertIsNone(self.d.claim('W1'))
 def test_13_traversal(self):p=packet('PT');p['payload']['relative_output_path']='../x';p['packet_sha256']=packet_hash(p);self.d.enqueue(p);self.assertRaises(Unsafe,self.d.scan_once,'W1')
 def test_14_outbox_persist(self):p=packet('OP');self.d.enqueue(p);self.d.scan_once('W1');self.assertTrue(self.d.outbox_path(p).exists())
 def test_15_tokens(self):self.d.enqueue(packet('S','A'));self.d.enqueue(packet('S','B'));self.assertEqual(self.d.scan_once('W1')['status'],'COMPLETED');self.assertEqual(self.d.scan_once('W1')['status'],'COMPLETED')
 def test_16_hash(self):p=packet('HH');p['packet_sha256']='0'*64;self.assertRaises(Invalid,self.d.enqueue,p)
 def test_17_action(self):p=packet('A');p['action']='SHELL';self.bad(p)
 def test_18_prepared_fault(self):p=packet('F1');self.d.enqueue(p);c=self.d.claim('W1');self.assertRaises(FaultInjected,self.d.submit_result,c,'W1',c.lease_generation,None,'after_prepared_before_side_effect')
 def test_19_side_effect_fault(self):p=packet('F2');self.d.enqueue(p);c=self.d.claim('W1');self.assertRaises(FaultInjected,self.d.submit_result,c,'W1',c.lease_generation,None,'after_side_effect_before_result')
 def test_20_result_fault(self):p=packet('F3');self.d.enqueue(p);c=self.d.claim('W1');self.assertRaises(FaultInjected,self.d.submit_result,c,'W1',c.lease_generation,None,'after_result_before_outbox')
 def test_21_outbox_fault(self):p=packet('F4');self.d.enqueue(p);c=self.d.claim('W1');self.assertRaises(FaultInjected,self.d.submit_result,c,'W1',c.lease_generation,None,'after_outbox_before_registry')
 def test_22_registry_fault(self):p=packet('F5');self.d.enqueue(p);c=self.d.claim('W1');self.assertRaises(FaultInjected,self.d.submit_result,c,'W1',c.lease_generation,None,'after_registry_before_committed')
 def test_23_cleanup_fault(self):p=packet('F6');self.d.enqueue(p);c=self.d.claim('W1');self.assertRaises(FaultInjected,self.d.submit_result,c,'W1',c.lease_generation,None,'after_committed_before_running_cleanup');d2=LocalRelayDispatcher(self.root,[self.base]);self.assertEqual(d2.read_task_state('F6')['state'],'completed')
 def test_24_outbox_only(self):p=packet('OO');self.d.enqueue(p);c=self.d.claim('W1');self.assertRaises(FaultInjected,self.d.submit_result,c,'W1',c.lease_generation,None,'after_outbox_before_registry');LocalRelayDispatcher(self.root,[self.base]);self.assertIsNotNone(self.d.read_completed_record('OO'))
 def test_25_registry_only(self):p=packet('RO');self.d.enqueue(p);self.d.scan_once('W1');self.d.outbox_path(p).unlink();LocalRelayDispatcher(self.root,[self.base]);self.assertTrue(self.d.outbox_path(p).exists())
 def test_26_whitespace(self):p=packet('W');p['objective']=' ';self.bad(p)
 def test_27_timestamp(self):p=packet('TS');p['created_at']='2026-01-01';self.bad(p)
 def test_28_lease_low(self):self.bad(packet('LL',lease=4))
 def test_29_lease_high(self):self.bad(packet('LH',lease=3601))
 def test_30_empty_allowlist(self):self.assertRaises(Unsafe,LocalRelayDispatcher,self.root,[])
 def test_31_sibling_prefix(self):self.assertRaises(Unsafe,LocalRelayDispatcher,self.base/'runtime2',[self.base/'runtime'])
 def test_32_unknown_field(self):p=packet('UF');p['x']=1;self.bad(p)
 def test_33_array_elements(self):p=packet('AR');p['success_criteria']=[''];self.bad(p)
 def test_34_bad_target(self):self.bad(packet('BT',target='worker'))
 def test_35_generation_first(self):self.d.enqueue(packet('G1'));self.assertEqual(self.d.claim('W1').lease_generation,1)
 def test_36_generation_restart(self):t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(packet('G2',lease=5));self.d.claim('W1',t);self.d.recover(t+timedelta(seconds=6));d2=LocalRelayDispatcher(self.root,[self.base]);self.assertEqual(d2.claim('W2',t+timedelta(seconds=6)).lease_generation,2)
 def test_37_recovery_count(self):t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(packet('RC',lease=5));self.d.claim('W1',t);self.d.recover(t+timedelta(seconds=6));self.assertEqual(self.d.read_task_state('RC')['recovery_count'],1)
 def test_38_stale_claim(self):t=datetime(2026,1,1,tzinfo=timezone.utc);self.d.enqueue(packet('SC',lease=5));old=self.d.claim('W1',t);self.d.recover(t+timedelta(seconds=6));self.d.claim('W2',t+timedelta(seconds=6));self.assertRaises(Invalid,self.d.submit_result,old,'W1',old.lease_generation,t+timedelta(seconds=6))
 def test_39_stale_generation(self):self.d.enqueue(packet('SG'));c=self.d.claim('W1');self.assertRaises(Invalid,self.d.heartbeat,c,'W1',999)
 def test_40_cancelled(self):p=packet('CAN');self.d.enqueue(p);self.d.cancel_task('CAN');self.assertIsNone(self.d.claim('W1'))
 def test_41_completed_regression(self):p=packet('CR');self.d.enqueue(p);self.d.scan_once('W1');self.assertRaises(Invalid,self.d._task_record,p,'running')
 def test_42_checkpoint(self):self.d.enqueue(packet('CP'));c=self.d.claim('W1');cp=self.d.read_checkpoint('CP');self.assertEqual(cp['claim_id'],c.claim_id);self.assertIn('highest_progress_token',cp)
 def test_43_checkpoint_monotonic(self):p=packet('CM');self.d.enqueue(p);c=self.d.claim('W1');a=self.d.read_checkpoint('CM')['highest_progress_token'];self.d.heartbeat(c,'W1',c.lease_generation);b=self.d.read_checkpoint('CM')['highest_progress_token'];self.assertGreaterEqual(b,a)
 def test_44_dispatcher_state(self):s=self.d.state();self.assertIn('runtime_root_allowlist_digest',s);self.assertIn('counters',s)
 def test_45_registry_fields(self):p=packet('RF');self.d.enqueue(p);self.d.scan_once('W1');r=self.d.read_completed_record('RF');self.assertTrue({'task_id','action','result_hash','outbox_path','completed_at','claim_id','lease_generation','recovery_count','checkpoint_ref'}<=set(r))
 def test_46_adapter(self):self.assertTrue(all(hasattr(self.a,x) for x in ('claim','heartbeat','submit_result','recover','read_task_state','read_checkpoint','read_completed_record')))
 def test_47_conflict_blocked(self):p=packet('BC');self.d.enqueue(p);self.d.scan_once('W1');o=self.d.read_json(self.d.outbox_path(p));o['worker_id']='evil';self.d.write_json(self.d.outbox_path(p),o);a=self.d.reconcile();self.assertTrue(any(x['status']=='BLOCKED' for x in a));self.assertEqual(self.d.read_task_state('BC')['state'],'blocked')
 def test_48_schema(self):p=packet('SV');p['schema_version']='x';self.bad(p)
 def test_49_symlink_escape(self):
  outside=self.base/'outside';outside.mkdir();link=self.root/'state'/'link'
  try:link.symlink_to(outside,target_is_directory=True)
  except OSError:self.skipTest('symlink unsupported')
  self.assertRaises(Unsafe,self.d.safe_path,'state','link','x')
 def test_50_outbox_exact(self):p=packet('OE');self.d.enqueue(p);self.d.scan_once('W1');r=self.d.read_completed_record('OE');self.assertEqual(self.root/r['outbox_path'],self.d.outbox_path(p))
if __name__=='__main__':unittest.main(verbosity=2)
