from __future__ import annotations

import unittest

from autonomy_signal import derive_next_issue, generate_signal, render_markdown


def base_state() -> dict:
    return {
        "schema_version": "2.0",
        "mission_id": "LCR-AUTONOMY-0002",
        "status": "BUILDING",
        "step_id": 2,
        "attempt": 0,
        "current_role": "LCR-B",
        "next_role": "LCR-B",
        "mission_result": None,
        "pending_packet": None,
        "stable_ref": "nav-relay-mvp-0001",
        "lease": None,
        "cloud_activation": {},
        "metabolism": {"rollback_anchor": "nav-relay-mvp-0001"},
    }


class AutonomySignalTests(unittest.TestCase):
    def test_active_human_gate_emits_requires_human_issue(self):
        state = base_state()
        state["status"] = "HUMAN_GATE"
        state["current_role"] = "HUMAN"
        state["human_gate"] = {
            "code": "CLOUD_ACTIVATION_REQUIRES_HUMAN",
            "blocker": "Need cloud model authentication.",
            "required_action": "Authorize credentials outside L2.",
        }
        issue = derive_next_issue(state)
        self.assertEqual(issue["kind"], "activation_gate")
        self.assertTrue(issue["requires_human"])
        self.assertFalse(issue["can_auto_execute"])

    def test_deferred_activation_gate_is_not_hidden_while_building(self):
        state = base_state()
        state["deferred_human_gate"] = {
            "code": "CLOUD_ACTIVATION_REQUIRES_HUMAN",
            "status": "DEFERRED_NOT_OVERRIDDEN",
            "blocker": "Need default-branch launcher authorization.",
        }
        issue = derive_next_issue(state)
        self.assertEqual(issue["kind"], "activation_gate")
        self.assertTrue(issue["requires_human"])

    def test_pending_handoff_is_actionable_without_human(self):
        state = base_state()
        state["status"] = "READY_FOR_VERIFY"
        state["current_role"] = "LCR-C"
        state["next_role"] = "LCR-C"
        state["pending_packet"] = "packets/B-TO-C.json"
        issue = derive_next_issue(state)
        self.assertEqual(issue["kind"], "handoff")
        self.assertFalse(issue["requires_human"])
        self.assertTrue(issue["can_auto_execute"])
        self.assertIn("B-TO-C.json", issue["summary"])

    def test_idle_pass_has_no_next_issue(self):
        state = base_state()
        state["status"] = "IDLE"
        state["current_role"] = "LCR-A"
        state["next_role"] = "LCR-A"
        state["mission_result"] = "PASS"
        self.assertIsNone(derive_next_issue(state))

    def test_dedupe_key_is_stable_across_generation_time(self):
        state = base_state()
        state["deferred_human_gate"] = {
            "code": "CLOUD_ACTIVATION_REQUIRES_HUMAN",
            "status": "DEFERRED_NOT_OVERRIDDEN",
            "blocker": "Need launcher.",
        }
        first = generate_signal(state, generated_at="2026-08-11T09:00:00+00:00")
        second = generate_signal(state, generated_at="2026-08-11T10:00:00+00:00")
        self.assertEqual(
            first["next_issue"]["dedupe_key"],
            second["next_issue"]["dedupe_key"],
        )
        self.assertNotEqual(first["signal_sha256"], second["signal_sha256"])

    def test_markdown_surfaces_progress_and_issue(self):
        state = base_state()
        state["deferred_human_gate"] = {
            "code": "CLOUD_ACTIVATION_REQUIRES_HUMAN",
            "status": "DEFERRED_NOT_OVERRIDDEN",
            "blocker": "Need launcher.",
        }
        signal = generate_signal(state, generated_at="2026-08-11T09:00:00+00:00")
        text = render_markdown(signal)
        self.assertIn("Development Progress", text)
        self.assertIn("Next issue", text)
        self.assertIn(signal["next_issue"]["dedupe_key"], text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
