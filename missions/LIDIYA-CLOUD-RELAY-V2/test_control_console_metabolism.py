import unittest
from control_console_metabolism import classify, compact

class MetabolismTests(unittest.TestCase):
    def test_duplicate_transient_is_waste(self):
        self.assertEqual(classify({'path':'scratch/event.json','kind':'progress_event','reproducible':True,'duplicate':True}),'WASTE')
    def test_sensitive_name_is_quarantined(self):
        self.assertEqual(classify({'path':'scratch/credential.txt','kind':'progress_event','reproducible':True}),'QUARANTINE')
    def test_protected_evidence_is_kept(self):
        self.assertEqual(classify({'path':'evidence/pass.json','kind':'progress_event','reproducible':True}),'KEEP')
    def test_content_not_retained(self):
        out=compact([{'id':'1','path':'scratch/a','kind':'progress_event','reproducible':True,'duplicate':True,'content':'discard-me'}])
        self.assertFalse(out['raw_content_retained'])
        self.assertNotIn('content',str(out))
    def test_deterministic_dedupe(self):
        item={'id':'1','path':'scratch/a','kind':'progress_event','reproducible':True,'duplicate':True}
        self.assertEqual(compact([item,item]),compact([item]))

if __name__ == '__main__': unittest.main()
