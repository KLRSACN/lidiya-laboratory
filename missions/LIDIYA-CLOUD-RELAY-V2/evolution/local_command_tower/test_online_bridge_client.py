import tempfile, unittest
from pathlib import Path
from bridge_protocol import make_task_envelope, make_evidence_envelope, EnvelopeError
from online_bridge_client import FileSpoolBridge, BridgeSpoolError

class BridgeTests(unittest.TestCase):
    def setUp(self): self.td=tempfile.TemporaryDirectory(); self.root=Path(self.td.name); self.b=FileSpoolBridge(self.root)
    def tearDown(self): self.td.cleanup()
    def task(self,seq=0,payload=None): return make_task_envelope(mission_id="LCR-EVOLUTION-0005",channel_id="online-local",sequence=seq,task_id=f"t{seq}",task_type="WAKE",payload=payload or {},authority_snapshot_hash="a")
    def test_accept_task_inside_workspace(self):
        r=self.b.ingest_task(self.task()); self.assertEqual(r["disposition"],"ACCEPTED"); self.assertTrue((self.root/r["path"]).exists())
    def test_duplicate_no_second_write(self):
        e=self.task(); self.b.ingest_task(e); r=self.b.ingest_task(e); self.assertEqual(r["disposition"],"ALREADY_SEEN_NO_WRITE"); self.assertEqual(len(self.b.list_spool()["inbox"]),1)
    def test_sequence_jump_rejected(self):
        self.b.ingest_task(self.task(0))
        with self.assertRaises(EnvelopeError): self.b.ingest_task(self.task(2))
    def test_tamper_rejected(self):
        e=self.task(); e["payload"]={"tampered":True}
        with self.assertRaises(EnvelopeError): self.b.ingest_task(e)
    def test_raw_chat_key_rejected(self):
        with self.assertRaises(BridgeSpoolError): self.b.ingest_task(self.task(payload={"raw_chat":"no"}))
    def test_nested_messages_rejected(self):
        with self.assertRaises(BridgeSpoolError): self.b.ingest_task(self.task(payload={"x":{"messages":[]}}))
    def test_spool_path_cannot_escape_workspace(self):
        with self.assertRaises(BridgeSpoolError): FileSpoolBridge(self.root,"../escape")
    def test_publish_evidence(self):
        e=make_evidence_envelope(mission_id="LCR-EVOLUTION-0005",channel_id="evidence",sequence=0,task_id="t0",result="PASS",evidence={"ok":True},parent_task_sha256="a"*64)
        r=self.b.publish_evidence(e); self.assertEqual(r["disposition"],"PUBLISHED"); self.assertEqual(len(self.b.list_spool()["outbox"]),1)

if __name__=="__main__": unittest.main()
