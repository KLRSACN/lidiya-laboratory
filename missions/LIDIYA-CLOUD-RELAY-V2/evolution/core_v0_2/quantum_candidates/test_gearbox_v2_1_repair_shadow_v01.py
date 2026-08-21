import tempfile
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gearbox_v2_1_repair_shadow_v01 import (
    AcceptedExperienceReceipt,
    GearboxGuardError,
    OperationalProgressReceipt,
    aggregate_events_shadow,
    canonical_event_id,
    canonical_event_kind,
    canonical_risk,
    select_gear_repair_shadow,
)

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
)


def exp_receipt(event_id="e1", kind="VERIFIED_RECOVERY", evidence="a" * 64):
    return AcceptedExperienceReceipt(
        event_id=event_id,
        event_kind=kind,
        evidence_sha256=evidence,
        verifier_role="LCR-C",
        verification_stage="C_VERIFIED",
        mission_id="LCR-EVOLUTION-0005",
        step_id=9,
    )


def op_receipt(event_id="o1", kind="DURABLE_PROGRESS", artifact="c" * 64):
    return OperationalProgressReceipt(
        event_id=event_id,
        event_kind=kind,
        artifact_sha256=artifact,
        source_role="W02-QUANTUM",
        mission_id="LCR-EVOLUTION-0005",
        step_id=9,
    )


class GearboxRepairShadowTests(unittest.TestCase):
    def test_rollback_outranks_standby_structurally(self):
        d = select_gear_repair_shadow(rollback_required=True, standby=True)
        self.assertEqual(d.selected_state, "R")
        self.assertTrue(d.terminal_precedence_applied)
        self.assertIn("rollback outranks standby", d.reason)

    def test_terminal_authority_precedes_malformed_nonessential_telemetry(self):
        d = select_gear_repair_shadow(
            rollback_required=True,
            standby=False,
            risk=None,
            context_load_ratio="bad",
            recent_shift_rate_ratio="bad",
        )
        self.assertEqual(d.selected_state, "R")

    def test_terminal_roundtrip_n_is_preserved_without_exit_authority(self):
        d = select_gear_repair_shadow(current_control_state="N")
        self.assertEqual(d.selected_state, "N")
        self.assertEqual(d.mode, "TERMINAL_AUTHORITY_SHADOW")

    def test_terminal_roundtrip_r_is_preserved_without_exit_authority(self):
        d = select_gear_repair_shadow(current_control_state="R")
        self.assertEqual(d.selected_state, "R")
        self.assertEqual(d.mode, "TERMINAL_AUTHORITY_SHADOW")

    def test_risk_none_does_not_alias_to_none_level(self):
        with self.assertRaises(GearboxGuardError):
            select_gear_repair_shadow(**{**BASE, "risk": None})

    def test_canonical_event_kind_is_one_typed_path(self):
        self.assertEqual(canonical_event_kind(" verified_recovery "), "VERIFIED_RECOVERY")
        for bad in (None, 1, [], {}):
            with self.subTest(value=bad):
                with self.assertRaises(GearboxGuardError):
                    canonical_event_kind(bad)

    def test_event_id_rejects_null_and_non_string(self):
        for bad in (None, True, 1, [], {}):
            with self.subTest(value=bad):
                with self.assertRaises(GearboxGuardError):
                    canonical_event_id(bad)

    def test_current_state_whitespace_is_canonicalized_once(self):
        d = select_gear_repair_shadow(**BASE, current_control_state=" G3 ")
        self.assertIn(d.selected_state, {"G1", "G2", "G3", "G4", "G5", "G6"})

    def test_raw_verified_claim_has_zero_credit_without_receipt(self):
        d = select_gear_repair_shadow(
            **{**BASE, "event_kind": "VERIFIED_RECOVERY", "event_independently_verified": True},
            current_control_state="G3",
        )
        self.assertEqual(d.verified_experience_delta, 0)
        self.assertFalse(d.real_experience_claim_allowed)

    def test_candidate_stage_cannot_mint_verified_credit_even_with_c_receipt(self):
        d = select_gear_repair_shadow(
            **{
                **BASE,
                "verification_stage": "CANDIDATE",
                "event_kind": "VERIFIED_RECOVERY",
                "event_independently_verified": True,
            },
            current_control_state="G3",
            accepted_experience_receipt=exp_receipt(),
        )
        self.assertEqual(d.verified_experience_delta, 0)
        self.assertFalse(d.real_experience_claim_allowed)

    def test_c_verified_matching_receipt_enables_shadow_verified_credit(self):
        d = select_gear_repair_shadow(
            **{**BASE, "event_kind": " verified_recovery ", "event_independently_verified": True},
            current_control_state="G3",
            accepted_experience_receipt=exp_receipt(),
        )
        self.assertEqual(d.verified_experience_delta, 4)
        self.assertTrue(d.real_experience_claim_allowed)
        self.assertEqual(d.credit_status, "SHADOW_RECEIPT_BOUND_ONLY")

    def test_operational_progress_is_separate_and_receipt_bound(self):
        raw = select_gear_repair_shadow(
            **{**BASE, "event_kind": "DURABLE_PROGRESS"}, current_control_state="G3"
        )
        self.assertEqual(raw.verified_experience_delta, 0)
        self.assertEqual(raw.operational_progress_delta, 0)
        accepted = select_gear_repair_shadow(
            **{**BASE, "event_kind": "DURABLE_PROGRESS"},
            current_control_state="G3",
            operational_progress_receipt=op_receipt(),
        )
        self.assertEqual(accepted.verified_experience_delta, 0)
        self.assertEqual(accepted.operational_progress_delta, 1)

    def test_inherited_safety_metadata_is_projected(self):
        d = select_gear_repair_shadow(
            **{**BASE, "risk": "CRITICAL"}, current_control_state="G6"
        )
        self.assertEqual(d.selected_state, "G1")
        self.assertEqual(d.guard_status, "BRAKE")
        self.assertTrue(d.receiver_ack_required)
        self.assertEqual(d.verification_gate, "C_VERIFIED")
        self.assertTrue(bool(d.return_condition))

    def test_rejected_first_claim_does_not_reserve_identity(self):
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td) / "registry.json"
            events = [
                {"event_id": "e1", "event_kind": "VERIFIED_RECOVERY"},
                {
                    "event_id": "e1",
                    "event_kind": "VERIFIED_RECOVERY",
                    "accepted_experience_receipt": exp_receipt(),
                },
            ]
            r = aggregate_events_shadow(events, registry_path=registry)
            self.assertEqual(r.rejected_unverified, 1)
            self.assertEqual(r.accepted_verified, 1)
            self.assertEqual(r.identity_conflicts, 0)

    def test_exact_replay_is_durable_noop_across_calls(self):
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td) / "registry.json"
            event = {
                "event_id": "e1",
                "event_kind": "VERIFIED_RECOVERY",
                "accepted_experience_receipt": exp_receipt(),
            }
            first = aggregate_events_shadow([event], registry_path=registry)
            second = aggregate_events_shadow([event], registry_path=registry)
            self.assertEqual(first.accepted_verified, 1)
            self.assertEqual(second.accepted_verified, 0)
            self.assertEqual(second.duplicate_events, 1)

    def test_same_evidence_new_id_is_lineage_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td) / "registry.json"
            first = {
                "event_id": "e1",
                "event_kind": "VERIFIED_RECOVERY",
                "accepted_experience_receipt": exp_receipt(event_id="e1", evidence="a" * 64),
            }
            second = {
                "event_id": "e2",
                "event_kind": "VERIFIED_RECOVERY",
                "accepted_experience_receipt": exp_receipt(event_id="e2", evidence="a" * 64),
            }
            r = aggregate_events_shadow([first, second], registry_path=registry)
            self.assertEqual(r.accepted_verified, 1)
            self.assertEqual(r.lineage_duplicates, 1)

    def test_same_id_different_binding_is_identity_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td) / "registry.json"
            first = {
                "event_id": "e1",
                "event_kind": "VERIFIED_RECOVERY",
                "accepted_experience_receipt": exp_receipt(event_id="e1", evidence="a" * 64),
            }
            second = {
                "event_id": "e1",
                "event_kind": "VERIFIED_RECOVERY",
                "accepted_experience_receipt": exp_receipt(event_id="e1", evidence="b" * 64),
            }
            r = aggregate_events_shadow([first, second], registry_path=registry)
            self.assertEqual(r.accepted_verified, 1)
            self.assertEqual(r.identity_conflicts, 1)

    def test_irrelevant_malformed_verifier_does_not_abort_batch(self):
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td) / "registry.json"
            valid = {
                "event_id": "e2",
                "event_kind": "VERIFIED_RECOVERY",
                "accepted_experience_receipt": exp_receipt(event_id="e2"),
            }
            r = aggregate_events_shadow([
                {"event_id": "w1", "event_kind": "WAIT", "independently_verified": "false"},
                valid,
            ], registry_path=registry)
            self.assertEqual(r.ignored_or_malformed, 1)
            self.assertEqual(r.accepted_verified, 1)

    def test_operational_receipt_is_durable_and_not_verified(self):
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td) / "registry.json"
            event = {
                "event_id": "o1",
                "event_kind": "DURABLE_PROGRESS",
                "independently_verified": "malformed but irrelevant",
                "operational_progress_receipt": op_receipt(),
            }
            r = aggregate_events_shadow([event], registry_path=registry)
            self.assertEqual(r.accepted_operational, 1)
            self.assertEqual(r.accepted_verified, 0)

    def test_outcome_accounting_conserves_input_records(self):
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td) / "registry.json"
            events = [
                None,
                {"event_id": "w1", "event_kind": "WAIT"},
                {"event_id": "e1", "event_kind": "VERIFIED_RECOVERY"},
                {
                    "event_id": "e2",
                    "event_kind": "VERIFIED_RECOVERY",
                    "accepted_experience_receipt": exp_receipt(event_id="e2"),
                },
                {
                    "event_id": "o1",
                    "event_kind": "DURABLE_PROGRESS",
                    "operational_progress_receipt": op_receipt(),
                },
            ]
            r = aggregate_events_shadow(events, registry_path=registry)
            self.assertEqual(r.total_outcomes, len(events))


if __name__ == "__main__":
    unittest.main()
