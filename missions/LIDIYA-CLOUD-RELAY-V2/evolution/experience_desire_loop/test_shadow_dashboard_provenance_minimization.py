import math
import unittest

from live_shadow_dashboard_event_adapter import (
    AUTOBIOGRAPHICAL_ELIGIBILITY_UNKNOWN,
    MAX_SUMMARY_CHARS,
    TRUST_REFERENCE_BOUND,
    TRUST_UNKNOWN,
    adapt_shadow_event,
)


class ShadowDashboardProvenanceMinimizationTests(unittest.TestCase):
    def _record(self, provenance):
        return {
            "event_type": "EXPERIENCE_APPRAISAL",
            "entity_id": "evt-1",
            "summary": "bounded summary",
            "provenance": provenance,
        }

    def _bound_provenance(self):
        return {
            "source_fingerprint": "sha256:abc",
            "source_event_id": "event-1",
            "appraisal_id": "appraisal-1",
            "appraisal_fingerprint": "sha256:appraisal",
            "verifier_envelope_hash": "sha256:verifier",
            "appraisal_policy_hash": "sha256:policy",
            "anchor_registry_hash": "sha256:anchor",
            "acceptance_record_id": "acceptance-1",
            "acceptance_record_hash": "sha256:acceptance",
            "acceptance_registry_snapshot_hash": "sha256:snapshot",
        }

    def _outcome(self, *, namespace="AUTOBIOGRAPHICAL", producer_eligible=None):
        outcome = {
            "closure_id": "closure-1",
            "closure_hash": "sha256:closure",
            "direction": "CONFIRM_MODEL",
            "target_namespace": namespace,
            "prediction_id": "prediction-1",
            "observation_id": "observation-1",
            "source_event_hash": "sha256:event",
        }
        if producer_eligible is not None:
            outcome["autobiographical_experience_eligible"] = producer_eligible
        return outcome

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

    def test_non_scalar_summary_is_rejected_not_stringified(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["summary"] = {"secret": "must-not-stringify"}
        with self.assertRaises(ValueError):
            adapt_shadow_event(record)

    def test_producer_authored_verified_pass_is_ignored_without_binding(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["trust_status"] = "VERIFIED_PASS"
        rendered = adapt_shadow_event(record)
        self.assertEqual(rendered["trust_status"], TRUST_UNKNOWN)
        self.assertNotEqual(rendered["trust_status"], "VERIFIED_PASS")

    def test_complete_acceptance_reference_set_is_still_unverified_display_binding(self):
        record = self._record(self._bound_provenance())
        record["trust_status"] = "TRUSTED"
        rendered = adapt_shadow_event(record)
        self.assertEqual(rendered["trust_status"], TRUST_REFERENCE_BOUND)
        self.assertNotIn(rendered["trust_status"], {"TRUSTED", "PASS", "VERIFIED_PASS"})

    def test_quarantine_reason_projects_enum_and_reference_hashes_only(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["event_type"] = "QUARANTINE"
        record["quarantine_reason"] = {
            "reason_code": "LEDGER_TAMPER",
            "source_reference_hash": "sha256:source",
            "detail_reference_hash": "sha256:detail",
            "raw_payload": {"secret": "must-not-surface"},
            "free_text": "producer-authored explanation",
        }
        rendered = adapt_shadow_event(record)
        self.assertEqual(
            rendered["quarantine_reason"],
            {
                "reason_code": "LEDGER_TAMPER",
                "source_reference_hash": "sha256:source",
                "detail_reference_hash": "sha256:detail",
            },
        )

    def test_unknown_quarantine_reason_code_renders_unknown_unverified(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["quarantine_reason"] = {
            "reason_code": "PRODUCER_SAYS_TRUST_ME",
            "raw": {"secret": "hidden"},
        }
        rendered = adapt_shadow_event(record)
        self.assertEqual(rendered["quarantine_reason"], {"reason_code": "UNKNOWN_UNVERIFIED"})

    def test_prediction_outcome_projects_only_canonical_scalar_surface(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["event_type"] = "OUTCOME_CLOSURE"
        record["prediction_outcome"] = {
            "closure_id": "closure-1",
            "closure_hash": "sha256:closure",
            "direction": "INCREASE_CAUTION",
            "target_namespace": "MODEL_LEARNED_SLOW_PLANNING",
            "prediction_id": "prediction-1",
            "observation_id": "observation-1",
            "source_event_hash": "sha256:event",
            "value_error": -0.2,
            "harm_error": 0.3,
            "total_error": 0.25,
            "planning_delta_candidate": 0.21,
            "autobiographical_experience_eligible": False,
            "raw_observation": {"secret": "must-not-surface"},
            "debug_payload": ["private", "nested"],
        }
        rendered = adapt_shadow_event(record)
        projected = rendered["prediction_outcome"]
        self.assertEqual(projected["closure_id"], "closure-1")
        self.assertEqual(projected["closure_hash"], "sha256:closure")
        self.assertEqual(projected["direction"], "INCREASE_CAUTION")
        self.assertEqual(
            projected["target_namespace"], "MODEL_LEARNED_SLOW_PLANNING"
        )
        self.assertNotIn("raw_observation", projected)
        self.assertNotIn("debug_payload", projected)
        self.assertNotIn("autobiographical_experience_eligible", projected)
        self.assertEqual(
            projected["autobiographical_experience_eligibility_status"],
            AUTOBIOGRAPHICAL_ELIGIBILITY_UNKNOWN,
        )

    def test_forged_true_with_valid_shaped_unknown_closure_never_renders_true(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["event_type"] = "OUTCOME_CLOSURE"
        record["prediction_outcome"] = self._outcome(producer_eligible=True)
        projected = adapt_shadow_event(record)["prediction_outcome"]
        self.assertNotIn("autobiographical_experience_eligible", projected)
        self.assertEqual(
            projected["autobiographical_experience_eligibility_status"],
            AUTOBIOGRAPHICAL_ELIGIBILITY_UNKNOWN,
        )
        self.assertNotEqual(
            projected["autobiographical_experience_eligibility_status"], True
        )

    def test_model_learned_slow_planning_producer_true_never_renders_autobiographical_true(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["event_type"] = "OUTCOME_CLOSURE"
        record["prediction_outcome"] = self._outcome(
            namespace="MODEL_LEARNED_SLOW_PLANNING", producer_eligible=True
        )
        projected = adapt_shadow_event(record)["prediction_outcome"]
        self.assertNotIn("autobiographical_experience_eligible", projected)
        self.assertEqual(
            projected["autobiographical_experience_eligibility_status"],
            AUTOBIOGRAPHICAL_ELIGIBILITY_UNKNOWN,
        )

    def test_producer_eligibility_type_or_value_is_non_authoritative_and_ignored(self):
        for forged in (True, False, "VERIFIED", {"eligible": True}, [True], 1):
            with self.subTest(forged=forged):
                record = self._record({"source_fingerprint": "sha256:abc"})
                record["event_type"] = "OUTCOME_CLOSURE"
                outcome = self._outcome()
                outcome["autobiographical_experience_eligible"] = forged
                record["prediction_outcome"] = outcome
                projected = adapt_shadow_event(record)["prediction_outcome"]
                self.assertNotIn("autobiographical_experience_eligible", projected)
                self.assertEqual(
                    projected["autobiographical_experience_eligibility_status"],
                    AUTOBIOGRAPHICAL_ELIGIBILITY_UNKNOWN,
                )

    def test_prediction_outcome_requires_canonical_reference_pair(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["prediction_outcome"] = {
            "direction": "CONFIRM_MODEL",
            "target_namespace": "MODEL_LEARNED_SLOW_PLANNING",
            "raw": {"secret": "must-not-surface"},
        }
        with self.assertRaises(ValueError):
            adapt_shadow_event(record)

    def test_nested_prediction_metric_is_rejected(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["prediction_outcome"] = {
            "closure_id": "closure-1",
            "closure_hash": "sha256:closure",
            "direction": "CONFIRM_MODEL",
            "target_namespace": "MODEL_LEARNED_SLOW_PLANNING",
            "total_error": {"secret": "nested"},
        }
        with self.assertRaises(ValueError):
            adapt_shadow_event(record)

    def test_non_finite_prediction_metrics_are_rejected_fail_closed(self):
        for metric_name in ("value_error", "harm_error", "total_error", "planning_delta_candidate"):
            for bad in (math.nan, math.inf, -math.inf):
                with self.subTest(metric_name=metric_name, bad=bad):
                    record = self._record({"source_fingerprint": "sha256:abc"})
                    record["event_type"] = "OUTCOME_CLOSURE"
                    outcome = self._outcome(namespace="MODEL_LEARNED_SLOW_PLANNING")
                    outcome[metric_name] = bad
                    record["prediction_outcome"] = outcome
                    with self.assertRaisesRegex(ValueError, f"NON_FINITE_OUTCOME_METRIC:{metric_name}"):
                        adapt_shadow_event(record)

    def test_finite_prediction_metrics_remain_projectable(self):
        record = self._record({"source_fingerprint": "sha256:abc"})
        record["event_type"] = "OUTCOME_CLOSURE"
        outcome = self._outcome(namespace="MODEL_LEARNED_SLOW_PLANNING")
        outcome.update({
            "value_error": -0.25,
            "harm_error": 0.0,
            "total_error": 0.125,
            "planning_delta_candidate": 1.0,
        })
        record["prediction_outcome"] = outcome
        projected = adapt_shadow_event(record)["prediction_outcome"]
        for key in ("value_error", "harm_error", "total_error", "planning_delta_candidate"):
            self.assertTrue(math.isfinite(projected[key]))

    def test_malformed_entity_id_is_rejected_not_stringified(self):
        for bad in ({"id": "evt-1"}, ["evt-1"], None, ""):
            with self.subTest(bad=bad):
                record = self._record({"source_fingerprint": "sha256:abc"})
                record["entity_id"] = bad
                with self.assertRaises(ValueError):
                    adapt_shadow_event(record)

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
