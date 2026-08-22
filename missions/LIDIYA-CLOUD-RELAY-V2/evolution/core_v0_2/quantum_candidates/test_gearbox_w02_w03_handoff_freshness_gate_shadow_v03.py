import copy
import unittest

from gearbox_w02_w03_handoff_freshness_gate_shadow_v01 import ExpectedHandoffSnapshot, HandoffFreshnessGateError
from gearbox_w02_w03_handoff_freshness_gate_shadow_v03 import (
    ExpectedHandoffV03Snapshot,
    REQUIRED_ADJUDICATION_CLAUSES_V03,
    validate_w02_to_w03_handoff_v03,
)


def packet():
    return {
        "schema_version": "1.4",
        "handoff_id": "W02-TO-W03-GEARBOX-EVIDENCE-20260822-2108",
        "source": "W02-QUANTUM",
        "target": "W03-SPIRIT",
        "formal_effect": "NONE_NONFORMAL_REVIEW_EVIDENCE_ONLY",
        "mission_state": {"git_blob_sha": "e32e01fa304a857f5185951443682ea937335473", "step_id": 9, "status": "STEP_DONE", "current_role": "LCR-A", "pending_packet": None, "v1": "VERIFIED_PASS"},
        "review_target": {"veto": "SPIRIT-MOD-GB21-047", "candidate_version": "V05", "required_regression": "MOVING_PROVIDER_HEAD_REESTABLISHMENT_NON_TERMINAL_AB"},
        "current_w02_review": {"review_id": "QUANTUM-GEARBOX-REPAIR-SHADOW-20260822-2008", "git_blob_sha": "1" * 40},
        "current_nav": {"synthesis_id": "NAV-GEARBOX-V2.1-W04-20260822-W02-2008-SYNTHESIS", "git_blob_sha": "2" * 40, "verdict": "BOUNDED_VETO"},
        "current_spirit_gate": {
            "version": "V03",
            "source_git_blob_sha": "3" * 40,
            "test_git_blob_sha": "4" * 40,
            "contract_git_blob_sha": "5" * 40,
            "workflow_git_blob_sha": "6" * 40,
            "workflow_update_commit": "7" * 40,
        },
        "exact_current_candidate": {"source_git_blob_sha": "8" * 40, "test_git_blob_sha": "9" * 40, "contract_git_blob_sha": "a" * 40},
        "visible_executable_evidence": {"workflow_run_id": 32524738088, "job_id": 96904287434, "job_conclusion": "success", "artifact_id": 9461767094, "artifact_zip_sha256": "b" * 64, "regression_counts": {"V01": "9/9", "V03": "9/9", "V04": "5/5", "V05": "4/4", "total": "27/27"}},
        "requested_spirit_adjudication": list(REQUIRED_ADJUDICATION_CLAUSES_V03),
        "response_to_open_veto": {
            "SPIRIT-MOD-GB21-047": "V05 is evidence-bound; fresh W03 exact-V05 adjudication remains mandatory.",
            "SPIRIT-MOD-GB21-046": "Terminal-exit remains inactive until fresh 047 closure passes review acceptance gate V03.",
        },
        "zero_learning_boundary": {"provider_head_churn_is_experience": False, "retry_backoff_is_experience": False, "recovery_duration_is_experience": False, "handoff_freshness_is_experience": False, "appraisal_delta": 0, "drive_delta": 0, "exploration_delta": 0, "preference_delta": 0, "personality_delta": 0, "trauma_relief_delta": 0, "p_base_mutation_allowed": False},
        "formal_c_pass_claimed": False,
        "production_provider_key_liveness_proven": False,
        "status": "READY_FOR_FRESH_W03_EXACT_V05_047_ADJUDICATION_W02_2008_NAV_2008_GATE_V03_BOUND",
    }


def expected():
    base = ExpectedHandoffSnapshot(
        mission_state_sha="e32e01fa304a857f5185951443682ea937335473",
        w02_review_id="QUANTUM-GEARBOX-REPAIR-SHADOW-20260822-2008", w02_review_sha="1" * 40,
        nav_synthesis_id="NAV-GEARBOX-V2.1-W04-20260822-W02-2008-SYNTHESIS", nav_sha="2" * 40,
        v05_source_sha="8" * 40, v05_test_sha="9" * 40, v05_contract_sha="a" * 40,
        spirit_gate_version="V03", spirit_gate_source_sha="3" * 40,
        workflow_run_id=32524738088, job_id=96904287434, artifact_id=9461767094, artifact_zip_sha256="b" * 64,
    )
    return ExpectedHandoffV03Snapshot(
        base=base,
        handoff_id="W02-TO-W03-GEARBOX-EVIDENCE-20260822-2108",
        spirit_gate_test_sha="4" * 40,
        spirit_gate_contract_sha="5" * 40,
        spirit_gate_workflow_sha="6" * 40,
        spirit_gate_workflow_commit="7" * 40,
    )


class HandoffFreshnessGateV03Tests(unittest.TestCase):
    def test_current_packet_passes_without_releasing_047(self):
        result = validate_w02_to_w03_handoff_v03(packet(), expected())
        self.assertEqual(result["status"], "HANDOFF_V03_FRESH_CURRENT_W02_2008_NAV_2008_EXACT_V05")
        self.assertTrue(result["review_acceptance_gate_v03_bound"])
        self.assertFalse(result["spirit_047_closed"])
        self.assertFalse(result["terminal_exit_activation_allowed"])

    def test_schema_14_is_supported_by_base_gate(self):
        validate_w02_to_w03_handoff_v03(packet(), expected())

    def test_stale_w02_review_fails_closed(self):
        p = packet(); p["current_w02_review"]["review_id"] = "QUANTUM-GEARBOX-REPAIR-SHADOW-20260822-1906"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v03(p, expected())

    def test_stale_nav_fails_closed(self):
        p = packet(); p["current_nav"]["synthesis_id"] = "NAV-GEARBOX-V2.1-W04-20260822-W02-1906-SYNTHESIS"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v03(p, expected())

    def test_gate_v02_downgrade_fails_closed(self):
        p = packet(); p["current_spirit_gate"]["version"] = "V02"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v03(p, expected())

    def test_gate_workflow_substitution_fails_closed(self):
        p = packet(); p["current_spirit_gate"]["workflow_git_blob_sha"] = "f" * 40
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v03(p, expected())

    def test_partial_v05_counts_fail_closed(self):
        p = packet(); p["visible_executable_evidence"]["regression_counts"]["total"] = "26/27"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v03(p, expected())

    def test_missing_eventual_reentry_clause_fails_closed(self):
        p = packet(); p["requested_spirit_adjudication"].remove(REQUIRED_ADJUDICATION_CLAUSES_V03[3])
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v03(p, expected())

    def test_terminal_exit_activation_before_w03_fails_closed(self):
        p = packet(); p["response_to_open_veto"]["SPIRIT-MOD-GB21-046"] = "Terminal exit active after V03 authored"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v03(p, expected())

    def test_learning_or_production_escalation_fails_closed(self):
        for mutation in ("personality_delta", "production"):
            p = packet()
            if mutation == "personality_delta": p["zero_learning_boundary"]["personality_delta"] = 1
            else: p["production_provider_key_liveness_proven"] = True
            with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v03(p, expected())


if __name__ == "__main__":
    unittest.main()
