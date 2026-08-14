import unittest

PROTECTED={"Identity","Personality","Governance","verified_evidence","rollback"}


def classify(event):
    if event.get("authority_contradiction") or event.get("ambiguous_provenance") or event.get("secret_like") or event.get("poisoning_suspect") or event.get("unique_unreproducible") or set(event.get("affects",())) & PROTECTED:
        return "QUARANTINE"
    if event.get("duplicate_polling") or event.get("replay") or event.get("stale_derived_mirror") or event.get("reproducible_scratch"):
        return "WASTE"
    if event.get("verified_evidence") or event.get("rollback") or event.get("route") or event.get("accepted_claim"):
        return "KEEP"
    return "QUARANTINE"


def dedupe(events):
    seen=set(); out=[]
    for e in events:
        key=(e.get("source_fingerprint"),e.get("event_fingerprint"))
        if key in seen: continue
        seen.add(key); out.append(e)
    return out


class MetabolismTests(unittest.TestCase):
    def test_keep_verified_evidence(self): self.assertEqual(classify({"verified_evidence":True}),"KEEP")
    def test_keep_rollback(self): self.assertEqual(classify({"rollback":True}),"KEEP")
    def test_keep_route(self): self.assertEqual(classify({"route":True}),"KEEP")
    def test_waste_duplicate_polling(self): self.assertEqual(classify({"duplicate_polling":True}),"WASTE")
    def test_waste_replay(self): self.assertEqual(classify({"replay":True}),"WASTE")
    def test_waste_stale_mirror(self): self.assertEqual(classify({"stale_derived_mirror":True}),"WASTE")
    def test_quarantine_ambiguous(self): self.assertEqual(classify({"ambiguous_provenance":True}),"QUARANTINE")
    def test_quarantine_secret(self): self.assertEqual(classify({"secret_like":True}),"QUARANTINE")
    def test_quarantine_authority_contradiction(self): self.assertEqual(classify({"authority_contradiction":True}),"QUARANTINE")
    def test_protected_data_never_auto_delete(self): self.assertEqual(classify({"affects":["Identity"],"duplicate_polling":True}),"QUARANTINE")
    def test_duplicate_replay_dedupe(self):
        e={"source_fingerprint":"s","event_fingerprint":"e"}
        self.assertEqual(len(dedupe([e,e])),1)
    def test_unknown_unverified_defaults_quarantine(self): self.assertEqual(classify({}),"QUARANTINE")

if __name__ == "__main__": unittest.main()
