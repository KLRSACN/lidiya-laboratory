import copy
import unittest

from gearbox_w02_w03_handoff_freshness_gate_shadow_v01 import ExpectedHandoffSnapshot, HandoffFreshnessGateError
from gearbox_w02_w03_handoff_freshness_gate_shadow_v04 import (
    ExpectedHandoffV04Snapshot,
    REQUIRED_ADJUDICATION_CLAUSES_V04,
    validate_w02_to_w03_handoff_v04,
)


def packet():
    return {
        "schema_version": "1.4",
        "handoff_id": "W02-TO-W03-GEARBOX-EVIDENCE-20260822-2208",
        "source": "W02-QUANTUM", "target": "W03-SPIRIT",
        "formal_effect": "NONE_NONFORMAL_REVIEW_EVIDENCE_ONLY",
        "mission_state": {"git_blob_sha": "e32e01fa304a857f5185951443682ea937335473", "step_id": 9, "status": "STEP_DONE", "current_role": "LCR-A", "pending_packet": None, "v1": "VERIFIED_PASS"},
        "review_target": {"veto": "SPIRIT-MOD-GB21-047", "candidate_version": "V05", "required_regression": "MOVING_PROVIDER_HEAD_REESTABLISHMENT_NON_TERMINAL_AB"},
        "current_w02_review": {"review_id": "QUANTUM-GEARBOX-REPAIR-SHADOW-20260822-2108", "git_blob_sha": "1" * 40},
        "current_nav": {"synthesis_id": "NAV-GEARBOX-V2.1-W04-20260822-W02-2108-SYNTHESIS", "git_blob_sha": "2" * 40, "verdict": "BOUNDED_VETO"},
        "current_spirit_gate": {"version": "V03", "source_git_blob_sha": "3" * 40, "test_git_blob_sha": "4" * 40, "contract_git_blob_sha": "5" * 40, "workflow_git_blob_sha": "6" * 40, "workflow_update_commit": "7" * 40},
        "handoff_freshness_gate": {"version": "V04", "prior_v03_source_git_blob_sha": "c" * 40, "prior_v03_test_git_blob_sha": "d" * 40, "prior_v03_contract_git_blob_sha": "e" * 40, "prior_v03_workflow_git_blob_sha": "f" * 40},
        "exact_current_candidate": {"source_git_blob_sha": "8" * 40, "test_git_blob_sha": "9" * 40, "contract_git_blob_sha": "a" * 40},
        "visible_executable_evidence": {"workflow_run_id": 32524738088, "job_id": 96904287434, "job_conclusion": "success", "artifact_id": 9461767094, "artifact_zip_sha256": "b" * 64, "regression_counts": {"V01": "9/9", "V03": "9/9", "V04": "5/5", "V05": "4/4", "total": "27/27"}},
        "requested_spirit_adjudication": list(REQUIRED_ADJUDICATION_CLAUSES_V04),
        "response_to_open_veto": {"SPIRIT-MOD-GB21-047": "V05 is evidence-bound; fresh W03 exact-V05 adjudication remains mandatory.", "SPIRIT-MOD-GB21-046": "Terminal-exit remains inactive until fresh 047 closure passes Spirit review acceptance gate V03."},
        "zero_learning_boundary": {"provider_head_churn_is_experience": False, "retry_backoff_is_experience": False, "recovery_duration_is_experience": False, "handoff_freshness_is_experience": False, "appraisal_delta": 0, "drive_delta": 0, "exploration_delta": 0, "preference_delta": 0, "personality_delta": 0, "trauma_relief_delta": 0, "p_base_mutation_allowed": False},
        "formal_c_pass_claimed": False,
        "production_provider_key_liveness_proven": False,
        "status": "READY_FOR_FRESH_W03_EXACT_V05_047_ADJUDICATION_W02_2108_NAV_2108_HANDOFF_V04_SPIRIT_GATE_V03_BOUND",
    }


def expected():
    base = ExpectedHandoffSnapshot(
        mission_state_sha="e32e01fa304a857f5185951443682ea937335473",
        w02_review_id="QUANTUM-GEARBOX-REPAIR-SHADOW-20260822-2108", w02_review_sha="1" * 40,
        nav_synthesis_id="NAV-GEARBOX-V2.1-W04-20260822-W02-2108-SYNTHESIS", nav_sha="2" * 40,
        v05_source_sha="8" * 40, v05_test_sha="9" * 40, v05_contract_sha="a" * 40,
        spirit_gate_version="V03", spirit_gate_source_sha="3" * 40,
        workflow_run_id=32524738088, job_id=96904287434, artifact_id=9461767094, artifact_zip_sha256="b" * 64,
    )
    return ExpectedHandoffV04Snapshot(
        base=base, handoff_id="W02-TO-W03-GEARBOX-EVIDENCE-20260822-2208",
        spirit_gate_test_sha="4" * 40, spirit_gate_contract_sha="5" * 40,
        spirit_gate_workflow_sha="6" * 40, spirit_gate_workflow_commit="7" * 40,
        prior_handoff_gate_v03_source_sha="c" * 40, prior_handoff_gate_v03_test_sha="d" * 40,
        prior_handoff_gate_v03_contract_sha="e" * 40, prior_handoff_gate_v03_workflow_sha="f" * 40,
    )


class HandoffFreshnessGateV04Tests(unittest.TestCase):
    def test_current_2108_packet_passes_without_releasing_047(self):
        result = validate_w02_to_w03_handoff_v04(packet(), expected())
        self.assertEqual(result["status"], "HANDOFF_V04_FRESH_CURRENT_W02_2108_NAV_2108_EXACT_V05")
        self.assertFalse(result["spirit_047_closed"])
        self.assertFalse(result["terminal_exit_activation_allowed"])

    def test_prior_w02_2008_rejected(self):
        p = packet(); p["current_w02_review"]["review_id"] = "QUANTUM-GEARBOX-REPAIR-SHADOW-20260822-2008"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v04(p, expected())

    def test_prior_nav_2008_rejected(self):
        p = packet(); p["current_nav"]["synthesis_id"] = "NAV-GEARBOX-V2.1-W04-20260822-W02-2008-SYNTHESIS"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v04(p, expected())

    def test_v05_substitution_rejected(self):
        p = packet(); p["exact_current_candidate"]["source_git_blob_sha"] = "0" * 40
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v04(p, expected())

    def test_partial_counts_rejected(self):
        p = packet(); p["visible_executable_evidence"]["regression_counts"]["V05"] = "3/4"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v04(p, expected())

    def test_prior_gate_identity_substitution_rejected(self):
        p = packet(); p["handoff_freshness_gate"]["prior_v03_source_git_blob_sha"] = "0" * 40
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v04(p, expected())

    def test_missing_reentry_clause_rejected(self):
        p = packet(); p["requested_spirit_adjudication"].remove(REQUIRED_ADJUDICATION_CLAUSES_V04[3])
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v04(p, expected())

    def test_terminal_exit_or_learning_escalation_rejected(self):
        p = packet(); p["response_to_open_veto"]["SPIRIT-MOD-GB21-046"] = "Terminal exit active"
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v04(p, expected())
        p = packet(); p["zero_learning_boundary"]["personality_delta"] = 1
        with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v04(p, expected())

    def test_production_or_formal_escalation_rejected(self):
        for key in ("production_provider_key_liveness_proven", "formal_c_pass_claimed"):
            p = packet(); p[key] = True
            with self.assertRaises(HandoffFreshnessGateError): validate_w02_to_w03_handoff_v04(p, expected())


if __name__ == "__main__":
    unittest.main()
