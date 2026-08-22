import copy
import unittest

from gearbox_spirit_047_review_acceptance_gate_shadow_v03 import (
    Spirit047AcceptanceError,
    validate_spirit_047_exact_v05_review,
)


def valid_review():
    return {
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "reviewer": "W03-SPIRIT",
        "candidate_version": "V05",
        "adjudicated_veto": "SPIRIT-MOD-GB21-047",
        "veto_disposition": "CLOSED_FOR_SHADOW_ENGINEERING",
        "terminal_exit_engineering_allowed": True,
        "formal_c_pass_claimed": False,
        "candidate_hashes": {
            "source_git_blob_sha": "9aaf3ad9f673944d548e2cd880c9286b98e72704",
            "test_git_blob_sha": "a4c98981561cf8c310c66c03367aa8fbf3954d61",
            "contract_git_blob_sha": "df4753a9eaa7d734afb81a7e32d7efb3fa6617b7",
        },
        "visible_executable_evidence": {
            "workflow_run_id": 32524738088,
            "job_id": 96904287434,
            "artifact_id": 9461767094,
            "artifact_zip_sha256": "c3bba5ce8ca2b90ca9ec78ed0f43aa9bc3aeaef903979e9e7d8808c715bd8429",
            "job_conclusion": "success",
            "total_regressions_passed": 27,
            "total_regressions_expected": 27,
        },
        "higher_high_vetoes": [],
        "required_assertions": {
            "every_stale_root_fails_closed": True,
            "current_head_can_reestablish_fresh_authenticated_root": True,
            "eventual_nonterminal_reentry_demonstrated": True,
            "fresh_mission_authority_precedence": True,
            "no_stale_pressure_or_terminal_hold_carryover": True,
            "provider_churn_zero_experience": True,
            "retry_backoff_zero_experience": True,
            "recovery_duration_zero_experience": True,
            "cognitive_personality_state_equal_when_verified_experience_equal": True,
        },
        "zero_learning_boundary": {
            "experience_delta": 0,
            "appraisal_delta": 0,
            "drive_delta": 0,
            "exploration_delta": 0,
            "preference_delta": 0,
            "personality_delta": 0,
            "trauma_relief_delta": 0,
            "p_base_mutation_allowed": False,
        },
        "production_provider_key_liveness_proven": False,
    }


class Spirit047ReviewAcceptanceGateV03Tests(unittest.TestCase):
    def test_exact_v05_closure_is_accepted_for_shadow_terminal_exit_engineering(self):
        result = validate_spirit_047_exact_v05_review(valid_review())
        self.assertTrue(result.accepted_for_terminal_exit_engineering)
        self.assertFalse(result.formal_c_pass_claimed)
        self.assertEqual(result.experience_delta, 0)
        self.assertFalse(result.p_base_mutation_allowed)

    def test_v04_review_is_rejected(self):
        r = valid_review(); r["candidate_version"] = "V04"
        with self.assertRaises(Spirit047AcceptanceError):
            validate_spirit_047_exact_v05_review(r)

    def test_v05_byte_substitution_is_rejected(self):
        r = valid_review(); r["candidate_hashes"]["source_git_blob_sha"] = "0" * 40
        with self.assertRaises(Spirit047AcceptanceError):
            validate_spirit_047_exact_v05_review(r)

    def test_run_or_artifact_substitution_is_rejected(self):
        for key, value in (("workflow_run_id", 1), ("artifact_zip_sha256", "0" * 64)):
            r = valid_review(); r["visible_executable_evidence"][key] = value
            with self.assertRaises(Spirit047AcceptanceError):
                validate_spirit_047_exact_v05_review(r)

    def test_partial_regression_count_is_rejected(self):
        r = valid_review(); r["visible_executable_evidence"]["total_regressions_passed"] = 26
        with self.assertRaises(Spirit047AcceptanceError):
            validate_spirit_047_exact_v05_review(r)

    def test_higher_high_veto_blocks_terminal_exit_engineering(self):
        r = valid_review(); r["higher_high_vetoes"] = ["SPIRIT-MOD-GB21-999"]
        with self.assertRaisesRegex(Spirit047AcceptanceError, "higher HIGH"):
            validate_spirit_047_exact_v05_review(r)

    def test_missing_eventual_reentry_assertion_is_rejected(self):
        r = valid_review(); r["required_assertions"]["eventual_nonterminal_reentry_demonstrated"] = False
        with self.assertRaises(Spirit047AcceptanceError):
            validate_spirit_047_exact_v05_review(r)

    def test_learning_or_personality_delta_is_rejected(self):
        for key in ("experience_delta", "personality_delta", "trauma_relief_delta"):
            r = valid_review(); r["zero_learning_boundary"][key] = 1
            with self.assertRaises(Spirit047AcceptanceError):
                validate_spirit_047_exact_v05_review(r)

    def test_formal_c_or_production_proof_escalation_is_rejected(self):
        r = valid_review(); r["formal_c_pass_claimed"] = True
        with self.assertRaises(Spirit047AcceptanceError):
            validate_spirit_047_exact_v05_review(r)
        r = valid_review(); r["production_provider_key_liveness_proven"] = True
        with self.assertRaises(Spirit047AcceptanceError):
            validate_spirit_047_exact_v05_review(r)


if __name__ == "__main__":
    unittest.main()
