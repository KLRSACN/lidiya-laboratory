import unittest
from core_v0_2.memory_index_adapter import MemorySource, build_manifest, route_sources, bootstrap_l0


class AdapterTests(unittest.TestCase):
    def source(self, **changes):
        values = dict(
            source_type="drive_doc",
            source_ref="doc1",
            fingerprint="abc",
            confidence=0.9,
            verified_count=2,
            last_verified="2026-08-13",
            ttl=3600,
            level="L1",
        )
        values.update(changes)
        return MemorySource(**values)

    def test_deterministic_dedup(self):
        item = self.source()
        self.assertEqual(build_manifest([item, item]), build_manifest([item]))

    def test_metadata_changes_hash(self):
        self.assertNotEqual(
            build_manifest([self.source()])["manifest_sha256"],
            build_manifest([self.source(ttl=7200)])["manifest_sha256"],
        )

    def test_protected_candidate_is_quarantined(self):
        manifest = build_manifest([self.source(affects=("Identity",))])
        self.assertEqual(manifest["sources"][0]["disposition"], "Quarantine")

    def test_ambiguous_source_is_quarantined(self):
        manifest = build_manifest([self.source(source_type="ambiguous")])
        self.assertEqual(manifest["sources"][0]["disposition"], "Quarantine")

    def test_secret_like_source_is_quarantined(self):
        manifest = build_manifest([self.source(source_type="secret_like")])
        self.assertEqual(manifest["sources"][0]["disposition"], "Quarantine")

    def test_contradictory_source_is_quarantined(self):
        manifest = build_manifest([self.source(contradictions=("conflicts-with-canonical",))])
        self.assertEqual(manifest["sources"][0]["disposition"], "Quarantine")

    def test_quarantined_source_is_not_routed(self):
        manifest = build_manifest([
            self.source(source_ref="safe", fingerprint="safe"),
            self.source(source_ref="blocked", fingerprint="blocked", source_type="ambiguous"),
        ])
        routed = route_sources(manifest, ["L1"])
        refs = {row["source_ref"] for row in routed}
        self.assertEqual(refs, {"safe"})

    def test_full_load_is_rejected(self):
        manifest = build_manifest([self.source()])
        with self.assertRaises(ValueError):
            route_sources(manifest, ["ALL"])
        with self.assertRaises(ValueError):
            route_sources(manifest, ["FULL"])

    def test_unknown_level_fails_closed(self):
        with self.assertRaises(ValueError):
            route_sources(build_manifest([self.source()]), ["L9"])

    def test_route_is_bounded(self):
        items = [
            self.source(source_ref="doc" + str(i), fingerprint=str(i))
            for i in range(20)
        ]
        self.assertEqual(len(route_sources(build_manifest(items), ["L1"], max_sources=8)), 8)

    def test_bootstrap_order(self):
        self.assertEqual(
            bootstrap_l0("index", ["00", "31", "32", "33"])["refs"],
            ["00", "31", "32", "33"],
        )

    def test_incorrect_bootstrap_order_fails_closed(self):
        with self.assertRaises(ValueError):
            bootstrap_l0("index", ["00", "32", "31", "33"])


if __name__ == "__main__":
    unittest.main()
