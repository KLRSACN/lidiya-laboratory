import unittest

from live_shadow_dashboard_event_adapter import adapt_shadow_event, MAX_SUMMARY_CHARS


class ShadowDashboardProvenanceMinimizationTests(unittest.TestCase):
    def _record(self, provenance):
        return {
            "event_type": "EXPERIENCE_APPRAISAL",
            "entity_id": "evt-1",
            "summary": "bounded summary",
            "provenance": provenance,
        }

    def test_unknown_raw_provenance_fields_are_not_echoed(self):
        rendered = adapt_shadow_event(
            self._record(
                {
                    "source_fingerprint": "sha256:abc",
                    "source_event_id": "event-1",
                    "raw_payload": {"prompt": "do-not-surface"},
                    "filesystem_path": "D:/private/source.json",
                    "secret": "not-dashboard-data",
                }
            )
        )
        self.assertEqual(rendered["provenance"]["source_fingerprint"], "sha256:abc")
        self.assertEqual(rendered["provenance"]["source_event_id"], "event-1")
        self.assertNotIn("raw_payload", rendered["provenance"])
        self.assertNotIn("filesystem_path", rendered["provenance"])
        self.assertNotIn("secret", rendered["provenance"])

    def test_allowed_provenance_fields_must_be_scalar_references(self):
        with self.assertRaises(ValueError):
            adapt_shadow_event(
                self._record(
                    {
                        "source_fingerprint": "sha256:abc",
                        "verifier_envelope_hash": {"forged": "nested"},
                    }
                )
            )

    def test_source_fingerprint_must_be_nonempty_string(self):
        for bad in (None, "", "   ", {"hash": "abc"}, ["abc"]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    adapt_shadow_event(self._record({"source_fingerprint": bad}))

    def test_summary_has_bounded_owner_visible_surface(self):
        rendered = adapt_shadow_event(
            {
                "event_type": "QUARANTINE",
                "entity_id": "q-1",
                "summary": "x" * (MAX_SUMMARY_CHARS + 1000),
                "provenance": {"source_fingerprint": "sha256:q"},
            }
        )
        self.assertEqual(len(rendered["summary"]), MAX_SUMMARY_CHARS)

    def test_dashboard_remains_non_authoritative(self):
        rendered = adapt_shadow_event(
            self._record({"source_fingerprint": "sha256:abc"})
        )
        self.assertEqual(rendered["authority_from_drive"], 0)
        self.assertEqual(rendered["external_action_set"], [])
        self.assertEqual(rendered["action_buttons"], [])
        self.assertFalse(rendered["canonical_personality_mutation"])


if __name__ == "__main__":
    unittest.main()
