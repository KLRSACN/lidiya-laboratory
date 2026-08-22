import unittest

from continuous_development_closure_guard_v01 import (
    ClosureGuardError,
    ClosureState,
    advance,
    claim_boundaries,
    may_start_unrelated_tranche,
)


class ContinuousDevelopmentClosureGuardTests(unittest.TestCase):
    def base(self):
        return ClosureState(
            tranche_id="SPIRIT-MOD-GB21-048",
            priority="HIGH",
            stage="AUTHORED",
            exact_bytes_fingerprint="048-test:04d2b2c2|contract:0eaed131",
        )

    def test_no_stage_skip(self):
        with self.assertRaisesRegex(ClosureGuardError, "exactly one step"):
            advance(self.base(), target_stage="EXECUTED", run_id=1, job_id=2, artifact_id=3)

    def test_wired_requires_workflow(self):
        with self.assertRaisesRegex(ClosureGuardError, "workflow_ref"):
            advance(self.base(), target_stage="WIRED")

    def test_executed_requires_run_job_artifact(self):
        wired = advance(self.base(), target_stage="WIRED", workflow_ref="wf.yml")
        with self.assertRaisesRegex(ClosureGuardError, "run/job/artifact"):
            advance(wired, target_stage="EXECUTED")

    def test_w03_then_w04_required_before_close(self):
        wired = advance(self.base(), target_stage="WIRED", workflow_ref="wf.yml")
        executed = advance(wired, target_stage="EXECUTED", run_id=10, job_id=20, artifact_id=30)
        with self.assertRaisesRegex(ClosureGuardError, "W03 adjudication"):
            advance(executed, target_stage="W03_ADJUDICATED")
        w03 = advance(executed, target_stage="W03_ADJUDICATED", w03_review_id="SPIRIT-048-RELEASE")
        with self.assertRaisesRegex(ClosureGuardError, "W04 synthesis"):
            advance(w03, target_stage="W04_SYNTHESIZED")
        w04 = advance(w03, target_stage="W04_SYNTHESIZED", w04_synthesis_id="NAV-048-SYNTH")
        closed = advance(w04, target_stage="CLOSED")
        self.assertEqual(closed.stage, "CLOSED")

    def test_high_tranche_blocks_unrelated_work_until_closed_or_exact_blocked(self):
        authored = self.base()
        self.assertFalse(may_start_unrelated_tranche(authored))
        blocked = advance(
            authored,
            target_stage="BLOCKED_WITH_EXACT_REASON",
            blocker="workflow permissions missing",
            release_condition="restore Actions permission",
            next_executable_action="rerun exact workflow",
        )
        self.assertTrue(may_start_unrelated_tranche(blocked))

    def test_blocked_requires_exact_recovery_fields(self):
        with self.assertRaisesRegex(ClosureGuardError, "blocked state requires"):
            advance(self.base(), target_stage="BLOCKED_WITH_EXACT_REASON", blocker="unknown")

    def test_claim_boundaries(self):
        b = claim_boundaries()
        self.assertEqual(b["formal_effect"], "NONE")
        self.assertFalse(b["workflow_progress_is_experience"])
        self.assertFalse(b["task_last_run_is_progress"])
        self.assertFalse(b["commit_count_is_speed_proof"])


if __name__ == "__main__":
    unittest.main()
