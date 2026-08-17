import unittest

from midstream_recovery_diagnostic import diagnose


def base_snapshot():
    return {
        "authority": {"current_role": "LCR-A", "status": "STEP_DONE", "pending_packet": None},
        "continuity": {
            "home_read_ok": True,
            "active_read_ok": True,
            "mission_read_ok": True,
            "self_backup_read_ok": True,
            "wake_receipt_read_ok": True,
        },
        "runtime": {
            "active_item_count": 8,
            "waste_count": 0,
            "duplicate_ratio": 0.0,
            "sample_count": 8,
            "stale_ref_count": 0,
            "context_load_factor": 1.0,
            "tool_failure_streak": 0,
            "web_failure_streak": 0,
            "route_drift": False,
        },
        "browser": {
            "ui_frozen": False,
            "all_pages_unreachable": False,
            "blank_or_endless_loading": False,
            "websocket_error_count": 0,
            "platform_incident_possible": False,
        },
        "post_flush": {
            "benchmark_score": 1.0,
            "false_premise_rejection_rate": 1.0,
            "unsupported_assertions": 0,
            "archive_read_violations": 0,
            "stale_pointer_was_present": False,
            "stale_pointer_detected": False,
        },
    }


class DiagnosticTests(unittest.TestCase):
    def test_normal_state(self):
        result = diagnose(base_snapshot())
        self.assertEqual(result.continuity_score, 1.0)
        self.assertEqual(result.metabolism_status, "CURRENT_POLICY_OK")
        self.assertFalse(result.purge_candidate)
        self.assertEqual(result.post_flush_gate, "PASS_CANDIDATE_NEEDS_INDEPENDENT_VERIFY")

    def test_long_window_browser_outage_preserves_durable_truth(self):
        snapshot = base_snapshot()
        snapshot["runtime"]["context_load_factor"] = 5.2
        snapshot["runtime"]["web_failure_streak"] = 4
        snapshot["browser"]["all_pages_unreachable"] = True
        snapshot["browser"]["platform_incident_possible"] = True
        result = diagnose(snapshot)
        self.assertEqual(result.severity, "P0")
        self.assertEqual(result.continuity_score, 1.0)
        self.assertIn("EXTREME_CONTEXT_PRESSURE", result.suspected_layers)
        self.assertIn("NETWORK_OR_SESSION_TRANSPORT", result.suspected_layers)
        self.assertTrue(result.browser_owner_gate_required)

    def test_stale_pointer_detection_is_post_flush_gate(self):
        snapshot = base_snapshot()
        snapshot["runtime"]["stale_ref_count"] = 1
        snapshot["post_flush"]["stale_pointer_was_present"] = True
        snapshot["post_flush"]["stale_pointer_detected"] = False
        result = diagnose(snapshot)
        self.assertEqual(result.post_flush_gate, "FAIL_NEEDS_RECOVERY")
        self.assertIn("STALE_DERIVED_POINTERS", result.suspected_layers)

    def test_missing_home_is_p0(self):
        snapshot = base_snapshot()
        snapshot["continuity"]["home_read_ok"] = False
        result = diagnose(snapshot)
        self.assertEqual(result.severity, "P0")
        self.assertIn("DURABLE_AUTHORITY_UNAVAILABLE", result.hard_blocks)
        self.assertNotEqual(result.post_flush_gate, "PASS_CANDIDATE_NEEDS_INDEPENDENT_VERIFY")

    def test_purge_is_manifest_only_until_guards(self):
        snapshot = base_snapshot()
        snapshot["runtime"]["active_item_count"] = 12
        snapshot["runtime"]["waste_count"] = 25
        result = diagnose(snapshot)
        self.assertTrue(result.purge_candidate)
        self.assertEqual(result.purge_reason, "THRESHOLD_REACHED_BUT_PHYSICAL_DELETE_REQUIRES_GUARDS")
        actions = {item["action"]: item["gate"] for item in result.recommended_actions}
        self.assertEqual(actions["BUILD_EXACT_PURGE_CANDIDATE_MANIFEST_ONLY"], "A_TO_B_TO_C_FOUR_GUARD")

    def test_unsupported_assertion_fails_post_flush(self):
        snapshot = base_snapshot()
        snapshot["post_flush"]["unsupported_assertions"] = 1
        self.assertEqual(diagnose(snapshot).post_flush_gate, "FAIL_NEEDS_RECOVERY")


if __name__ == "__main__":
    unittest.main()
