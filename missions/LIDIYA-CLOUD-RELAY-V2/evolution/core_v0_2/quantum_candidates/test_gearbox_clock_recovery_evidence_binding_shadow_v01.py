import copy
import unittest

from gearbox_clock_recovery_evidence_binding_shadow_v01 import (
    ClockRecoveryEvidenceManifest,
    EvidenceBindingGuardError,
    EXPECTED_ARTIFACT_ID,
    EXPECTED_ARTIFACT_ZIP_SHA256,
    EXPECTED_COUNTS,
    EXPECTED_JOB_ID,
    EXPECTED_RUN_ID,
    EXPECTED_V05_BLOBS,
    SCHEMA_VERSION,
    spirit_review_projection,
)


def manifest():
    return {
        "schema_version": SCHEMA_VERSION,
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "candidate_version": "V05",
        "run_id": EXPECTED_RUN_ID,
        "job_id": EXPECTED_JOB_ID,
        "artifact_id": EXPECTED_ARTIFACT_ID,
        "artifact_zip_sha256": EXPECTED_ARTIFACT_ZIP_SHA256,
        "job_conclusion": "success",
        "regression_counts": dict(EXPECTED_COUNTS),
        "v05_blobs": dict(EXPECTED_V05_BLOBS),
        "formal_effect": "NONE",
        "formal_c_verification": "NOT_CLAIMED",
        "synthetic_provider_is_production_proof": False,
    }


class ClockRecoveryEvidenceBindingShadowV01Tests(unittest.TestCase):
    def test_exact_current_visible_evidence_is_bound_for_spirit_review(self):
        verified = ClockRecoveryEvidenceManifest.verify(manifest())
        self.assertEqual(verified.candidate_version, "V05")
        projection = spirit_review_projection(manifest())
        self.assertEqual(projection["evidence_binding_status"], "EXACT_CURRENT_NONFORMAL_EXECUTABLE_EVIDENCE_BOUND")
        self.assertEqual(projection["regression_counts"]["V05"], 4)
        self.assertEqual(projection["experience_delta"], 0)
        self.assertEqual(projection["personality_delta"], 0)
        self.assertFalse(projection["p_base_mutation_allowed"])
        self.assertFalse(projection["production_provider_key_liveness_proven"])

    def test_artifact_digest_tamper_fails_closed(self):
        x = manifest(); x["artifact_zip_sha256"] = "0" * 64
        with self.assertRaisesRegex(EvidenceBindingGuardError, "artifact digest mismatch"):
            ClockRecoveryEvidenceManifest.verify(x)

    def test_wrong_run_job_or_artifact_identity_fails_closed(self):
        for field in ("run_id", "job_id", "artifact_id"):
            x = manifest(); x[field] += 1
            with self.subTest(field=field), self.assertRaises(EvidenceBindingGuardError):
                ClockRecoveryEvidenceManifest.verify(x)

    def test_regression_count_downgrade_fails_closed(self):
        x = manifest(); x["regression_counts"]["V05"] = 3
        with self.assertRaisesRegex(EvidenceBindingGuardError, "regression count binding mismatch"):
            ClockRecoveryEvidenceManifest.verify(x)

    def test_exact_current_blob_substitution_fails_closed(self):
        x = manifest(); x["v05_blobs"]["test"] = "0" * 40
        with self.assertRaisesRegex(EvidenceBindingGuardError, "exact-current V05 blob binding mismatch"):
            ClockRecoveryEvidenceManifest.verify(x)

    def test_failed_job_cannot_be_relabelled_as_visible_pass(self):
        x = manifest(); x["job_conclusion"] = "failure"
        with self.assertRaisesRegex(EvidenceBindingGuardError, "did not conclude success"):
            ClockRecoveryEvidenceManifest.verify(x)

    def test_nonformal_boundary_cannot_be_upgraded(self):
        x = manifest(); x["formal_c_verification"] = "PASS"
        with self.assertRaisesRegex(EvidenceBindingGuardError, "non-formal evidence boundary violated"):
            ClockRecoveryEvidenceManifest.verify(x)
        y = manifest(); y["synthetic_provider_is_production_proof"] = True
        with self.assertRaisesRegex(EvidenceBindingGuardError, "cannot become production proof"):
            ClockRecoveryEvidenceManifest.verify(y)


if __name__ == "__main__":
    unittest.main()
