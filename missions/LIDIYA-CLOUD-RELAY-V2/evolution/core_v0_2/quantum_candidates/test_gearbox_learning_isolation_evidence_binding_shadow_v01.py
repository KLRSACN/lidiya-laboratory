import copy
import unittest

from gearbox_learning_isolation_evidence_binding_shadow_v01 import (
    LearningIsolationEvidenceGuardError, LearningIsolationEvidenceManifest, review_projection,
)


def manifest():
    return {
        "schema_version":"0.1-shadow","mission_id":"LCR-EVOLUTION-0005","step_id":9,
        "run_id":101,"job_id":202,"artifact_id":303,"artifact_zip_sha256":"a"*64,
        "job_conclusion":"success",
        "suite_results":{"SIGNED_PRESSURE_CHRONICITY_NEUTRALITY_10000_AB":"success","RECOVERY_METADATA_END_TO_END_DATAFLOW_EXCLUSION":"success"},
        "bound_blobs":{"pressure_source":"1"*40,"pressure_test":"2"*40,"metadata_source":"3"*40,"metadata_test":"4"*40,"workflow":"5"*40},
        "experience_delta":0,"appraisal_delta":0,"drive_delta":0,"exploration_delta":0,"preference_delta":0,
        "personality_delta":0,"trauma_relief_delta":0,"p_base_mutation_allowed":False,
        "formal_effect":"NONE","formal_c_verification":"NOT_CLAIMED",
    }

class LearningIsolationEvidenceBindingTests(unittest.TestCase):
    def test_exact_success_manifest_projects_nonformal_boundary(self):
        p = review_projection(manifest())
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

    def test_cognitive_delta_rejected(self):
        for field in ("experience_delta","appraisal_delta","drive_delta","exploration_delta","preference_delta","personality_delta","trauma_relief_delta"):
            m=manifest(); m[field]=1
            with self.assertRaises(LearningIsolationEvidenceGuardError, msg=field): LearningIsolationEvidenceManifest.verify(m)

    def test_pbase_or_formal_promotion_rejected(self):
        for patch in ({"p_base_mutation_allowed":True},{"formal_effect":"PROMOTE"},{"formal_c_verification":"PASS"}):
            m=manifest(); m.update(patch)
            with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)

    def test_artifact_digest_or_blob_substitution_rejected(self):
        for field,value in (("artifact_zip_sha256","bad"),):
            m=manifest(); m[field]=value
            with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)
        m=manifest(); m["bound_blobs"]["pressure_source"]="bad"
        with self.assertRaises(LearningIsolationEvidenceGuardError): LearningIsolationEvidenceManifest.verify(m)

if __name__ == "__main__": unittest.main()
