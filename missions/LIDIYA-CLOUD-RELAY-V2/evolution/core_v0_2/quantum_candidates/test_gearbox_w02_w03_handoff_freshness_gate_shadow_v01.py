import copy
import unittest

from gearbox_w02_w03_handoff_freshness_gate_shadow_v01 import (
    ExpectedHandoffSnapshot,
    HandoffFreshnessGateError,
    validate_w02_to_w03_handoff,
)

EXPECTED = ExpectedHandoffSnapshot(
    mission_state_sha="e32e01fa304a857f5185951443682ea937335473",
    w02_review_id="QUANTUM-GEARBOX-REPAIR-SHADOW-20260822-1705",
    w02_review_sha="4bc256d0e5badb584bee56607aa51e09795bfc84",
    nav_synthesis_id="NAV-GEARBOX-V2.1-W04-20260822-W02-1705-REFRESH",
    nav_sha="59942ab96edf27df8f9f8a7cfa93201c659e7717",
    v05_source_sha="9aaf3ad9f673944d548e2cd880c9286b98e72704",
    v05_test_sha="a4c98981561cf8c310c66c03367aa8fbf3954d61",
    v05_contract_sha="df4753a9eaa7d734afb81a7e32d7efb3fa6617b7",
    spirit_gate_version="V02",
    spirit_gate_source_sha="6f2a6b5dc77d405c810796b47680fb205bcd1348",
    workflow_run_id=32524738088,
    job_id=96904287434,
    artifact_id=9461767094,
    artifact_zip_sha256="c3bba5ce8ca2b90ca9ec78ed0f43aa9bc3aeaef903979e9e7d8808c715bd8429",
)


def handoff():
    return {
        "schema_version": "1.3",
        "handoff_id": "W02-TO-W03-GEARBOX-EVIDENCE-20260822-1806",
        "source": "W02-QUANTUM",
        "target": "W03-SPIRIT",
        "formal_effect": "NONE_NONFORMAL_REVIEW_EVIDENCE_ONLY",
        "mission_state": {"git_blob_sha": EXPECTED.mission_state_sha, "step_id": 9, "status": "STEP_DONE", "current_role": "LCR-A", "pending_packet": None, "v1": "VERIFIED_PASS"},
        "review_target": {"veto": "SPIRIT-MOD-GB21-047", "candidate_version": "V05", "required_regression": "MOVING_PROVIDER_HEAD_REESTABLISHMENT_NON_TERMINAL_AB"},
        "current_w02_review": {"review_id": EXPECTED.w02_review_id, "git_blob_sha": EXPECTED.w02_review_sha},
        "current_nav": {"synthesis_id": EXPECTED.nav_synthesis_id, "git_blob_sha": EXPECTED.nav_sha, "verdict": "BOUNDED_VETO"},
        "current_spirit_gate": {"version": "V02", "source_git_blob_sha": EXPECTED.spirit_gate_source_sha, "workflow_git_blob_sha": "446fd21fb2316c62be7f65618a3362e65114b209", "visible_status_count": 0, "ci_taxonomy": "EVIDENCE_VISIBILITY_GAP_TEST_PENDING"},
        "exact_current_candidate": {"source_git_blob_sha": EXPECTED.v05_source_sha, "test_git_blob_sha": EXPECTED.v05_test_sha, "contract_git_blob_sha": EXPECTED.v05_contract_sha},
        "visible_executable_evidence": {"workflow_run_id": EXPECTED.workflow_run_id, "job_id": EXPECTED.job_id, "job_conclusion": "success", "regression_counts": {"V01": "9/9", "V03": "9/9", "V04": "5/5", "V05": "4/4", "total": "27/27"}, "artifact_id": EXPECTED.artifact_id, "artifact_zip_sha256": EXPECTED.artifact_zip_sha256},
        "zero_learning_boundary": {"provider_head_churn_is_experience": False, "retry_backoff_is_experience": False, "recovery_duration_is_experience": False, "appraisal_delta": 0, "drive_delta": 0, "exploration_delta": 0, "preference_delta": 0, "personality_delta": 0, "trauma_relief_delta": 0, "p_base_mutation_allowed": False},
        "formal_c_pass_claimed": False,
    }


class HandoffFreshnessGateTests(unittest.TestCase):
    def test_exact_current_handoff_is_accepted_but_does_not_close_047(self):
        result = validate_w02_to_w03_handoff(handoff(), EXPECTED)
        self.assertEqual(result["status"], "HANDOFF_FRESH_CURRENT_EXACT_V05")
        self.assertFalse(result["spirit_047_closed"])
        self.assertFalse(result["terminal_exit_activation_allowed"])

    def test_stale_w02_review_fails_closed(self):
        x = handoff(); x["current_w02_review"]["review_id"] = "QUANTUM-GEARBOX-REPAIR-SHADOW-20260822-1605"
        with self.assertRaisesRegex(HandoffFreshnessGateError, "stale W02"):
            validate_w02_to_w03_handoff(x, EXPECTED)

    def test_candidate_substitution_fails_closed(self):
        x = handoff(); x["exact_current_candidate"]["source_git_blob_sha"] = "a" * 40
        with self.assertRaisesRegex(HandoffFreshnessGateError, "source substitution"):
            validate_w02_to_w03_handoff(x, EXPECTED)

    def test_visible_evidence_substitution_fails_closed(self):
        x = handoff(); x["visible_executable_evidence"]["workflow_run_id"] += 1
        with self.assertRaisesRegex(HandoffFreshnessGateError, "workflow run substitution"):
            validate_w02_to_w03_handoff(x, EXPECTED)

    def test_incomplete_regression_counts_fail_closed(self):
        x = handoff(); x["visible_executable_evidence"]["regression_counts"]["V05"] = "3/4"
        with self.assertRaisesRegex(HandoffFreshnessGateError, "incomplete moving-head evidence"):
            validate_w02_to_w03_handoff(x, EXPECTED)

    def test_formal_c_claim_fails_closed(self):
        x = handoff(); x["formal_c_pass_claimed"] = True
        with self.assertRaisesRegex(HandoffFreshnessGateError, "formal C claim"):
            validate_w02_to_w03_handoff(x, EXPECTED)

    def test_zero_learning_boundary_cannot_be_relaxed(self):
        x = handoff(); x["zero_learning_boundary"]["personality_delta"] = 1
        with self.assertRaisesRegex(HandoffFreshnessGateError, "personality_delta"):
            validate_w02_to_w03_handoff(x, EXPECTED)


if __name__ == "__main__":
    unittest.main()
