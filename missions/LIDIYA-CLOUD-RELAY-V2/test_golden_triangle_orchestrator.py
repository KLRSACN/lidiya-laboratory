import unittest
import golden_triangle_orchestrator as g

class GoldenTriangleTests(unittest.TestCase):
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
        p={'packet_sha256':'p','target':'LCR-B'}
        s={'current_role':'LCR-B','pending_packet_sha256':'p','consumed_packet_sha256':[]}
        n=g.consume_and_dispatch(s,p,'LCR-C')
        n['current_role']='LCR-B'; n['pending_packet_sha256']='p'
        with self.assertRaises(g.GuardError): g.consume_and_dispatch(n,p,'LCR-C')
    def test_roundtrip_shape(self):
        ab=g.make_handoff('LCR-A','LCR-B','root',2)
        bc=g.make_handoff('LCR-B','LCR-C',ab['packet_sha256'],2)
        ca=g.make_handoff('LCR-C','LCR-A',bc['packet_sha256'],2)
        self.assertEqual([ab['target'],bc['target'],ca['target']],['LCR-B','LCR-C','LCR-A'])

if __name__ == '__main__': unittest.main()
