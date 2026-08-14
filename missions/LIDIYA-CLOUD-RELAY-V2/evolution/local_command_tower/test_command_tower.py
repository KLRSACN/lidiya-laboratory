import tempfile, unittest
from pathlib import Path
from bridge_protocol import make_task_envelope, verify_envelope, ReplayGuard, EnvelopeError
from command_tower import Tower, serve
from standby_router import route

class TowerTests(unittest.TestCase):
    def setUp(self): self.td=tempfile.TemporaryDirectory(); self.root=Path(self.td.name); self.t=Tower(self.root,execute_enabled=False)
    def tearDown(self): self.td.cleanup()
    def test_health_loopback_contract(self):
        h=self.t.health(); self.assertTrue(h["ok"]); self.assertEqual(h["binding"],"LOOPBACK_ONLY")
    def test_wake_small_nest(self):
        out=self.t.wake(); self.assertEqual(out["status"],"WOKEN"); self.assertEqual(out["small_nest"]["runtime_state"],"READY")
    def test_public_bind_rejected(self):
        with self.assertRaises(ValueError): serve(self.t,"0.0.0.0",0)
    def test_standby_routes_command_without_model(self):
        d=route({"kind":"COMMAND"}); self.assertEqual(d["target"],"COMMAND_BROKER"); self.assertFalse(d["wake_model"])
    def test_model_work_routes_small_nest(self):
        d=route({"kind":"MODEL_ADAPTER"}); self.assertEqual(d["target"],"SMALL_NEST"); self.assertTrue(d["wake_model"])
    def test_canonical_task_hash_and_tamper(self):
        e=make_task_envelope(mission_id="m",channel_id="c",sequence=0,task_id="t",task_type="WAKE",payload={},authority_snapshot_hash="a"); self.assertTrue(verify_envelope(e,expected_mission="m")); e["payload"]={"x":1}
        with self.assertRaises(EnvelopeError): verify_envelope(e)
    def test_replay_guard_duplicate_noop(self):
        e=make_task_envelope(mission_id="m",channel_id="c",sequence=0,task_id="t",task_type="WAKE",payload={},authority_snapshot_hash="a"); g=ReplayGuard(); self.assertEqual(g.accept(e),"ACCEPTED"); self.assertEqual(g.accept(e),"ALREADY_SEEN")
    def test_replay_guard_sequence_jump(self):
        g=ReplayGuard(); a=make_task_envelope(mission_id="m",channel_id="c",sequence=0,task_id="a",task_type="WAKE",payload={},authority_snapshot_hash="a"); b=make_task_envelope(mission_id="m",channel_id="c",sequence=2,task_id="b",task_type="WAKE",payload={},authority_snapshot_hash="a"); g.accept(a)
        with self.assertRaises(EnvelopeError): g.accept(b)

if __name__=="__main__": unittest.main()
