import copy
import unittest

from gearbox_w02_w03_handoff_freshness_gate_shadow_v01 import ExpectedHandoffSnapshot
from gearbox_w02_w03_handoff_freshness_gate_shadow_v02 import (
    ExpectedHandoffSemanticSnapshot,
    HandoffFreshnessGateError,
    REQUIRED_ADJUDICATION_CLAUSES,
    validate_w02_to_w03_handoff_v02,
)


def packet():
    return {
        "schema_version": "1.3",
        "handoff_id": "W02-TO-W03-GEARBOX-EVIDENCE-20260822-1906",
        "source": "W02-QUANTUM",
        "target": "W03-SPIRIT",
        "formal_effect": "NONE_NONFORMAL_REVIEW_EVIDENCE_ONLY",
        "mission_state": {"git_blob_sha": "e32e01fa304a857f5185951443682ea937335473", "step_id": 9, "status": "STEP_DONE", "current_role": "LCR-A", "pending_packet": None, "v1": "VERIFIED_PASS"},
        "review_target": {"veto": "SPIRIT-MOD-GB21-047", "candidate_version": "V05", "required_regression": "MOVING_PROVIDER_HEAD_REESTABLISHMENT_NON_TERMINAL_AB"},
        "current_w02_review": {"review_id": "Q-1", "git_blob_sha": "1" * 40},
        "current_nav": {"synthesis_id": "NAV-1", "git_blob_sha": "2" * 40, "verdict": "BOUNDED_VETO"},
        "current_spirit_gate": {"version": "V02", "source_git_blob_sha": "3" * 40},
        "exact_current_candidate": {"source_git_blob_sha": "4" * 40, "test_git_blob_sha": "5" * 40, "contract_git_blob_sha": "6" * 40},
        "visible_executable_evidence": {"workflow_run_id": 10, "job_id": 11, "job_conclusion": "success", "artifact_id": 12, "artifact_zip_sha256": "a" * 64, "regression_counts": {"V01": "9/9", "V03": "9/9", "V04": "5/5", "V05": "4/4", "total": "27/27"}},
        "requested_spirit_adjudication": [
            "Review exact-current V05 Spirit-047, not V04.",
            "Use this exact W02 packet and reject older W02 handoffs.",
            "Confirm every stale root fails closed after legitimate provider-head advance.",
            "Confirm a quiet/current provider head can establish a fresh authenticated root under fresh Mission/current trust and ultimately re-enter.",
            "Confirm provider-head churn, root invalidation, retry/backoff and recovery duration remain zero Experience/appraisal/drive/exploration/preference/personality/P_base/trauma-relief.",
            "Report any new HIGH veto before terminal-exit activation.",
            "If 047 closes, emit a durable exact-V05 W03 review suitable for Spirit-047 gate V02 consumption.",
        ],
        "response_to_open_veto": {
            "SPIRIT-MOD-GB21-047": "V05 visible evidence is bound; fresh W03 adjudication remains mandatory.",
            "SPIRIT-MOD-GB21-046": "Terminal-exit remains inactive until 047 fresh closure is consumed through gate V02.",
        },
        "zero_learning_boundary": {"provider_head_churn_is_experience": False, "retry_backoff_is_experience": False, "recovery_duration_is_experience": False, "appraisal_delta": 0, "drive_delta": 0, "exploration_delta": 0, "preference_delta": 0, "personality_delta": 0, "trauma_relief_delta": 0, "p_base_mutation_allowed": False},
        "formal_c_pass_claimed": False,
        "production_provider_key_liveness_proven": False,
        "status": "READY_FOR_FRESH_W03_EXACT_V05_047_ADJUDICATION_W02_1906_BOUND",
    }


def expected():
    base = ExpectedHandoffSnapshot(
        mission_state_sha="e32e01fa304a857f5185951443682ea937335473",
        w02_review_id="Q-1", w02_review_sha="1" * 40,
        nav_synthesis_id="NAV-1", nav_sha="2" * 40,
        v05_source_sha="4" * 40, v05_test_sha="5" * 40, v05_contract_sha="6" * 40,
        spirit_gate_version="V02", spirit_gate_source_sha="3" * 40,
        workflow_run_id=10, job_id=11, artifact_id=12, artifact_zip_sha256="a" * 64,
    )
    return ExpectedHandoffSemanticSnapshot(base=base, handoff_id="W02-TO-W03-GEARBOX-EVIDENCE-20260822-1906")


class HandoffFreshnessGateV02Tests(unittest.TestCase):
    def test_complete_packet_passes_but_does_not_release_047(self):
        result = validate_w02_to_w03_handoff_v02(packet(), expected())
        self.assertEqual(result["status"], "HANDOFF_FRESH_CURRENT_EXACT_V05_SEMANTICALLY_COMPLETE")
        self.assertFalse(result["spirit_047_closed"])
        self.assertFalse(result["terminal_exit_activation_allowed"])

    def test_missing_required_adjudication_clause_fails_closed(self):
        p = packet(); p["requested_spirit_adjudication"].remove(REQUIRED_ADJUDICATION_CLAUSES[1])
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v02(p, expected())

    def test_wrong_handoff_identity_fails_closed(self):
        p = packet(); p["handoff_id"] = "stale"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v02(p, expected())

    def test_nav_verdict_relaxation_fails_closed(self):
        p = packet(); p["current_nav"]["verdict"] = "READY"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v02(p, expected())

    def test_production_proof_escalation_fails_closed(self):
        p = packet(); p["production_provider_key_liveness_proven"] = True
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v02(p, expected())

    def test_terminal_exit_must_remain_inactive(self):
        p = packet(); p["response_to_open_veto"]["SPIRIT-MOD-GB21-046"] = "terminal exit may activate now"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v02(p, expected())


if __name__ == "__main__":
    unittest.main()
