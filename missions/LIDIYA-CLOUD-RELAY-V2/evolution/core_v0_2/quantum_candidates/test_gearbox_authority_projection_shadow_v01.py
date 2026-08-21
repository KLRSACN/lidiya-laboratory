import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gearbox_controller import GearboxGuardError
from gearbox_authority_projection_shadow_v01 import (
    AuthorityDecisionEnvelope,
    PINNED_MISSION_STATE_BLOB_SHA,
    PINNED_STEP_ID,
    select_gear_with_authority_projection_shadow,
)
# Continuity/CI chaining: the already-executed authority suite also carries the
# signer-authenticity and authenticated new-epoch recovery regression classes.
# This keeps executable coverage moving even before the workflow exposes separate
# named outcome fields for those two sub-suites.
from test_gearbox_authority_experience_signer_shadow_v01 import SignerBoundaryTests
from test_gearbox_signer_epoch_recovery_shadow_v01 import SignerEpochRecoveryTests

BASE = dict(
    risk="LOW",
    uncertainty=0.1,
    evidence_quality=0.9,
    task_complexity=0.8,
    reversibility=True,
    storage_pressure_ratio=0.1,
    context_load_ratio=0.1,
    tool_failure_ratio=0.0,
    stale_pointer_ratio=0.0,
    route_drift=False,
    continuity_anchor_health=1.0,
    recovery_active=False,
    secretary_level="GREEN",
    verification_stage="C_VERIFIED",
    durable_progress_age_ratio=0.1,
    event_kind="WAIT",
    event_independently_verified=False,
    contradiction=False,
    hard_safety_conflict=False,
    rollback_required=False,
    standby=False,
    proposed_autonomy=6,
    current_control_state="G3",
)


def authority_envelope(
    *,
    selected_state="G1",
    mission_sha=PINNED_MISSION_STATE_BLOB_SHA,
    step_id=PINNED_STEP_ID,
    authority_role="LCR-A",
    formal_mutation_allowed=False,
):
    if selected_state == "R":
        guard = "ROLLBACK"
    elif selected_state == "N":
        guard = "HOLD"
    else:
        guard = "BRAKE"
    return AuthorityDecisionEnvelope(
        schema_version="1.0-shadow",
        mission_id="LCR-EVOLUTION-0005",
        step_id=step_id,
        authority_role=authority_role,
        mission_state_blob_sha=mission_sha,
        decision_id="authority-decision-001",
        selected_state=selected_state,
        guard_status=guard,
        return_condition="fresh authority re-evaluation required",
        checkpoint_required=True,
        receiver_ack_required=True,
        verification_gate="NOT_PROMOTION_EVIDENCE",
        formal_mutation_allowed=formal_mutation_allowed,
    )


class AuthorityProjectionShadowTests(unittest.TestCase):
    def test_authority_conflict_requires_exact_envelope(self):
        with self.assertRaises(GearboxGuardError):
            select_gear_with_authority_projection_shadow(
                authority_conflict=True,
                authority_decision_envelope=None,
                **BASE,
            )

    def test_fresh_authority_exact_result_overrides_permissive_fallback(self):
        d = select_gear_with_authority_projection_shadow(
            authority_conflict=True,
            authority_decision_envelope=authority_envelope(selected_state="G1"),
            **{**BASE, "risk": "LOW", "task_complexity": 1.0, "secretary_level": "GREEN"},
        )
        self.assertEqual(d.selected_state, "G1")
        self.assertEqual(d.mode, "FRESH_AUTHORITY_PROJECTION_SHADOW")
        self.assertEqual(d.guard_status, "BRAKE")
        self.assertFalse(d.formal_mutation_allowed)
        self.assertEqual(d.verified_experience_delta, 0)
        self.assertEqual(d.operational_progress_delta, 0)

    def test_authority_projection_precedes_malformed_nonessential_telemetry(self):
        d = select_gear_with_authority_projection_shadow(
            authority_conflict=True,
            authority_decision_envelope=authority_envelope(selected_state="R"),
            **{**BASE, "risk": None, "context_load_ratio": "bad", "recent_shift_rate_ratio": "bad"},
        )
        self.assertEqual(d.selected_state, "R")
        self.assertEqual(d.guard_status, "ROLLBACK")
        self.assertTrue(d.terminal_precedence_applied)

    def test_stale_authority_snapshot_fails_closed(self):
        with self.assertRaises(GearboxGuardError):
            select_gear_with_authority_projection_shadow(
                authority_conflict=True,
                authority_decision_envelope=authority_envelope(mission_sha="a" * 40),
                **BASE,
            )

    def test_caller_cannot_supply_matching_stale_expected_snapshot(self):
        stale = authority_envelope(mission_sha="a" * 40)
        with self.assertRaises(GearboxGuardError):
            select_gear_with_authority_projection_shadow(
                authority_conflict=True,
                authority_decision_envelope=stale,
                expected_mission_state_sha256="a" * 64,
                expected_step_id=PINNED_STEP_ID,
                **BASE,
            )

    def test_cross_step_authority_fails_closed(self):
        with self.assertRaises(GearboxGuardError):
            select_gear_with_authority_projection_shadow(
                authority_conflict=True,
                authority_decision_envelope=authority_envelope(step_id=8),
                **BASE,
            )

    def test_untrusted_authority_role_fails_closed(self):
        with self.assertRaises(GearboxGuardError):
            select_gear_with_authority_projection_shadow(
                authority_conflict=True,
                authority_decision_envelope=authority_envelope(authority_role="W07-SECRETARY"),
                **BASE,
            )

    def test_shadow_envelope_cannot_authorize_formal_mutation(self):
        with self.assertRaises(GearboxGuardError):
            select_gear_with_authority_projection_shadow(
                authority_conflict=True,
                authority_decision_envelope=authority_envelope(formal_mutation_allowed=True),
                **BASE,
            )

    def test_terminal_guard_must_match_terminal_state(self):
        good = authority_envelope(selected_state="R")
        bad = AuthorityDecisionEnvelope(**{**good.to_dict(), "guard_status": "HOLD"})
        with self.assertRaises(GearboxGuardError):
            select_gear_with_authority_projection_shadow(
                authority_conflict=True,
                authority_decision_envelope=bad,
                **BASE,
            )

    def test_without_conflict_existing_shadow_path_is_used(self):
        d = select_gear_with_authority_projection_shadow(
            authority_conflict=False,
            authority_decision_envelope=authority_envelope(selected_state="R"),
            **BASE,
        )
        self.assertNotEqual(d.mode, "FRESH_AUTHORITY_PROJECTION_SHADOW")
        self.assertNotEqual(d.selected_state, "R")


if __name__ == "__main__":
    unittest.main()
