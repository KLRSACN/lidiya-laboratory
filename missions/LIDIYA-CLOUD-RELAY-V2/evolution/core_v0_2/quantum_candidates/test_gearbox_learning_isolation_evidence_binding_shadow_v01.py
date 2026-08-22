import unittest

from gearbox_learning_isolation_evidence_binding_shadow_v01 import (
    LearningIsolationEvidenceGuardError, LearningIsolationEvidenceManifest, review_projection,
)


def blobs():
    return {
        "pressure_source":"1"*40,"pressure_test":"2"*40,"pressure_contract":"3"*40,
        "metadata_source":"4"*40,"metadata_test":"5"*40,"metadata_contract":"6"*40,
        "evidence_binding_source":"7"*40,"evidence_binding_test":"8"*40,"evidence_binding_contract":"9"*40,
        "workflow":"a"*40,
    }


def manifest():
    return {
        "schema_version":"0.2-shadow","mission_id":"LCR-EVOLUTION-0005","step_id":9,
        "run_id":101,"job_id":202,"artifact_id":303,"artifact_zip_sha256":"b"*64,
        "job_conclusion":"success",
        "suite_results":{"SIGNED_PRESSURE_CHRONICITY_NEUTRALITY_10000_AB":"success","RECOVERY_METADATA_END_TO_END_DATAFLOW_EXCLUSION":"success"},
        "bound_blobs":blobs(),
        "experience_delta":0,"appraisal_delta":0,"drive_delta":0,"exploration_delta":0,"preference_delta":0,
        "personality_delta":0,"trauma_relief_delta":0,"p_base_mutation_allowed":False,
        "formal_effect":"NONE","formal_c_verification":"NOT_CLAIMED",
    }

class LearningIsolationEvidenceBindingTests(unittest.TestCase):
    def test_exact_success_manifest_projects_nonformal_boundary(self):
        p = review_projection(manifest(), expected_blobs=blobs())
        self.assertEqual(p["status"], "NONFORMAL_LEARNING_ISOLATION_EVIDENCE_BOUND")
        self.assertFalse(p["whole_repository_taint_proof"])
        self.assertEqual(p["experience_delta"], 0)

    def test_missing_required_suite_rejected(self):
        m=manifest(); m["suite_results"].pop("RECOVERY_METADATA_END_TO_END_DATAFLOW_EXCLUSION")
        with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)

    def test_failed_suite_rejected(self):
        m=manifest(); m["suite_results"]["SIGNED_PRESSURE_CHRONICITY_NEUTRALITY_10000_AB"]="failure"
        with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)

    def test_extra_suite_cannot_substitute_required_identity(self):
        m=manifest(); m["suite_results"]["UNRELATED_PASS"]="success"
        with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)

    def test_missing_or_extra_blob_identity_rejected(self):
        m=manifest(); m["bound_blobs"].pop("pressure_contract")
        with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)
        m=manifest(); m["bound_blobs"]["unrelated_pass"]="c"*40
        with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)

    def test_expected_blob_substitution_rejected_even_when_shape_valid(self):
        m=manifest(); expected=blobs(); m["bound_blobs"]["workflow"]="d"*40
        with self.assertRaisesRegex(LearningIsolationEvidenceGuardError, "identity mismatch"):
            LearningIsolationEvidenceManifest.verify(m, expected_blobs=expected)

    def test_incomplete_expected_blob_set_rejected(self):
        expected=blobs(); expected.pop("metadata_contract")
        with self.assertRaises(LearningIsolationEvidenceGuardError):
            LearningIsolationEvidenceManifest.verify(manifest(), expected_blobs=expected)

    def test_cognitive_delta_rejected(self):
        for field in ("experience_delta","appraisal_delta","drive_delta","exploration_delta","preference_delta","personality_delta","trauma_relief_delta"):
            m=manifest(); m[field]=1
            with self.assertRaises(LearningIsolationEvidenceGuardError, msg=field): LearningIsolationEvidenceManifest.verify(m)

    def test_pbase_or_formal_promotion_rejected(self):
        for patch in ({"p_base_mutation_allowed":True},{"formal_effect":"PROMOTE"},{"formal_c_verification":"PASS"}):
            m=manifest(); m.update(patch)
            with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)

    def test_artifact_digest_or_blob_malformed_rejected(self):
        m=manifest(); m["artifact_zip_sha256"]="bad"
        with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)
        m=manifest(); m["bound_blobs"]["pressure_source"]="bad"
        with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)

if __name__ == "__main__": unittest.main()
