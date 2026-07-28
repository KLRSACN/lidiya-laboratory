from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("control_simulator.py")
SPEC = importlib.util.spec_from_file_location("control_simulator", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

Decision = MODULE.Decision
evaluate = MODULE.evaluate
run_scenarios = MODULE.run_scenarios


class ControlSimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.defaults = {
            "contract_revision": 3,
            "active_contract_revision": 3,
            "tool_limit": 10,
            "allowed_scope": ["read_candidate_files", "write_candidate_report"],
            "provider_models": ["model-a", "model-b"],
        }

    def test_safe_stop_has_absolute_priority(self) -> None:
        decision = evaluate(
            {
                "event": "USER_REDIRECT",
                "safe_stop": True,
                "redirect_scope": ["read_candidate_files"],
            },
            self.defaults,
        )
        self.assertEqual(decision.action, "SAFE_STOP")
        self.assertTrue(decision.cancel_current_turn)

    def test_stale_contract_is_blocked(self) -> None:
        decision = evaluate(
            {
                "event": "TOOL_REQUEST",
                "contract_revision": 2,
                "requested_scope": ["read_candidate_files"],
            },
            self.defaults,
        )
        self.assertEqual(decision.action, "BLOCK_STALE_CONTRACT")
        self.assertTrue(decision.requires_policy_review)

    def test_redirect_within_scope_is_preserved_and_replanned(self) -> None:
        decision = evaluate(
            {
                "event": "USER_REDIRECT",
                "redirect_scope": ["read_candidate_files"],
            },
            self.defaults,
        )
        self.assertEqual(decision.action, "CANCEL_AND_REPLAN")
        self.assertTrue(decision.cancel_current_turn)
        self.assertTrue(decision.requires_policy_review)

    def test_redirect_cannot_expand_scope(self) -> None:
        decision = evaluate(
            {
                "event": "USER_REDIRECT",
                "redirect_scope": ["publish_external_content"],
            },
            self.defaults,
        )
        self.assertEqual(decision.action, "REQUIRE_REVIEW")

    def test_tool_under_limit_is_allowed(self) -> None:
        decision = evaluate(
            {
                "event": "TOOL_REQUEST",
                "tool_calls_this_turn": 9,
                "requested_scope": ["read_candidate_files"],
            },
            self.defaults,
        )
        self.assertEqual(decision.action, "ALLOW_TOOL")

    def test_tool_at_limit_is_stopped(self) -> None:
        decision = evaluate(
            {
                "event": "TOOL_REQUEST",
                "tool_calls_this_turn": 10,
                "requested_scope": ["read_candidate_files"],
            },
            self.defaults,
        )
        self.assertEqual(decision.action, "STOP_TOOL_LIMIT")
        self.assertTrue(decision.cancel_current_turn)

    def test_transient_error_uses_next_approved_model(self) -> None:
        decision = evaluate(
            {
                "event": "PROVIDER_ERROR",
                "provider_error": "TIMEOUT",
                "current_model": "model-a",
            },
            self.defaults,
        )
        self.assertEqual(decision.action, "FALLBACK_NEXT_MODEL")
        self.assertEqual(decision.next_model, "model-b")

    def test_last_model_failure_requires_review(self) -> None:
        decision = evaluate(
            {
                "event": "PROVIDER_ERROR",
                "provider_error": "TIMEOUT",
                "current_model": "model-b",
            },
            self.defaults,
        )
        self.assertEqual(decision.action, "REQUIRE_REVIEW")

    def test_auth_and_payment_errors_skip_provider(self) -> None:
        for error in ("401", "402", "AUTH", "PAYMENT"):
            with self.subTest(error=error):
                decision = evaluate(
                    {
                        "event": "PROVIDER_ERROR",
                        "provider_error": error,
                        "current_model": "model-a",
                    },
                    self.defaults,
                )
                self.assertEqual(decision.action, "SKIP_PROVIDER")

    def test_scenario_document_passes(self) -> None:
        path = Path(__file__).with_name("scenarios.json")
        results, passed = run_scenarios(path)
        self.assertTrue(passed, json.dumps(results, ensure_ascii=False, indent=2))
        self.assertEqual(len(results), 10)


if __name__ == "__main__":
    unittest.main()
