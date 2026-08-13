import unittest

from core_v0_2.affective_store import VersionedAffectiveStore
from core_v0_2.memory_model import MemoryRecord, MemoryWeights


class AffectiveStoreTests(unittest.TestCase):
    def test_store_is_append_only_versioned_and_deduped(self):
        store = VersionedAffectiveStore()
        r1 = MemoryRecord(memory_id="m", timestamp="t1", event_summary="first", weights=MemoryWeights(W_self=0.8))
        c1 = store.append(r1)
        self.assertEqual(c1.version, 1)
        self.assertFalse(c1.deduplicated)
        same = store.append(r1)
        self.assertTrue(same.deduplicated)
        self.assertEqual(store.version, 1)
        r2 = MemoryRecord(memory_id="m", timestamp="t2", event_summary="re-evaluated", weights=MemoryWeights(W_self=0.9))
        c2 = store.append(r2)
        self.assertEqual(c2.version, 2)
        self.assertEqual(len(store.history("m")), 2)
        self.assertNotEqual(c1.snapshot_hash, c2.snapshot_hash)

    def test_store_delete_fails_closed(self):
        store = VersionedAffectiveStore()
        with self.assertRaises(RuntimeError):
            store.delete("m")


if __name__ == "__main__":
    unittest.main()
