import unittest
import golden_triangle_orchestrator as g

class GoldenTriangleTests(unittest.TestCase):
    def packet(self,target='LCR-B',source='LCR-A',parent='root',step=2):
        return g.make_handoff(source,target,parent,step)
    def state_for(self,p,target='LCR-B'):
        return {'current_role':target,'pending_packet':'packets/in.json','pending_packet_sha256':p['packet_sha256'],'consumed_packet_sha256':[]}
    def test_exact_slots(self):
        self.assertTrue(g.validate_slots({'LCR-A':1,'LCR-B':2,'LCR-C':3}))
        with self.assertRaises(g.GuardError): g.validate_slots({'LCR-A':1,'LCR-B':2})
    def test_exact_backups(self):
        self.assertTrue(g.validate_backups(g.BACKUPS))
        with self.assertRaises(g.GuardError): g.validate_backups(g.BACKUPS+('EXTRA',))
    def test_takeover_guard(self):
        r={'LCR-A':'a','LCR-B':'b','LCR-C':'c'}
        self.assertEqual(g.register_or_takeover(r,'LCR-B','b'),r)
        with self.assertRaises(g.GuardError): g.register_or_takeover(r,'LCR-C','new')
        h={'slot':'LCR-C','from':'c','to':'new','authorized':True}
        self.assertEqual(g.register_or_takeover(r,'LCR-C','new',h)['LCR-C'],'new')
    def test_replay_guard(self):
        p=self.packet(); s=self.state_for(p)
        n=g.consume_and_dispatch(s,p,'LCR-C')
        n['current_role']='LCR-B'; n['pending_packet']='packets/in.json'; n['pending_packet_sha256']=p['packet_sha256']
        with self.assertRaises(g.GuardError): g.consume_and_dispatch(n,p,'LCR-C')
    def test_mutated_packet_with_stale_hash_rejected(self):
        p=self.packet(); s=self.state_for(p)
        p['action']='MUTATED'
        with self.assertRaisesRegex(g.GuardError,'content hash mismatch'): g.consume_and_dispatch(s,p,'LCR-C')
    def test_restart_recovery_from_durable_state_only(self):
        inbound=self.packet(); s=self.state_for(inbound)
        outbound=self.packet(target='LCR-C',source='LCR-B',parent=inbound['packet_sha256'])
        n=g.consume_and_dispatch(s,inbound,'LCR-C','packets/out.json',outbound)
        recovered=g.recover_next_handoff(json_roundtrip(n))
        self.assertEqual(recovered,{'target':'LCR-C','pending_packet':'packets/out.json','pending_packet_sha256':outbound['packet_sha256']})
    def test_dispatch_requires_exact_next_packet(self):
        p=self.packet(); s=self.state_for(p)
        with self.assertRaises(g.GuardError): g.consume_and_dispatch(s,p,'LCR-C','packets/out.json')
    def test_roundtrip_shape(self):
        ab=g.make_handoff('LCR-A','LCR-B','root',2)
        bc=g.make_handoff('LCR-B','LCR-C',ab['packet_sha256'],2)
        ca=g.make_handoff('LCR-C','LCR-A',bc['packet_sha256'],2)
        self.assertEqual([ab['target'],bc['target'],ca['target']],['LCR-B','LCR-C','LCR-A'])

def json_roundtrip(obj):
    import json
    return json.loads(json.dumps(obj))

if __name__ == '__main__': unittest.main()
