import json
import tempfile
import unittest
from pathlib import Path

from gearbox_shift_history_shadow_v01 import (
    SOURCE_ROLE,
    ZERO_HASH,
    ShiftHistoryGuardError,
    append_shift_event,
    evaluate_thrash,
)


INSTALLATION = "inst-shadow-1"
RUNTIME = "runtime-shadow-1"
POLICY = {
    "window_size": 5,
    "minimum_support": 5,
    "enter_rate": 0.50,
    "exit_rate": 0.45,
    "z_value": 1.96,
}


def evidence(n: int) -> str:
    return f"{n:064x}"


class ShiftHistoryShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "shift-registry.json"
        self.head = ZERO_HASH
        self.seq = 0

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, *, event_id=None, from_gear="G2", to_gear="G3", evidence_n=None,
              previous=None, seq=None, installation=INSTALLATION, runtime=RUNTIME):
        target_seq = self.seq + 1 if seq is None else seq
        evidence_n = target_seq if evidence_n is None else evidence_n
        return {
            "event_id": event_id or f"shift-{target_seq}",
            "seq": target_seq,
            "from_gear": from_gear,
            "to_gear": to_gear,
            "evidence_sha256": evidence(evidence_n),
            "previous_event_hash": self.head if previous is None else previous,
            "installation_id": installation,
            "runtime_id": runtime,
            "source_role": SOURCE_ROLE,
        }

    def append(self, **kwargs):
        result = append_shift_event(
            self.event(**kwargs),
            registry_path=self.path,
            installation_id=INSTALLATION,
            runtime_id=RUNTIME,
        )
        if result.status == "ACCEPTED":
            self.seq += 1
            self.head = result.head_hash
        return result

    def test_append_only_sequence_and_hash_chain(self):
        first = self.append()
        second = self.append()
        self.assertEqual(first.status, "ACCEPTED")
        self.assertEqual(second.status, "ACCEPTED")
        self.assertEqual(second.accepted_count, 2)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["latest_seq"], 2)
        self.assertEqual(data["head_hash"], second.head_hash)

    def test_gap_sequence_fails_closed(self):
        with self.assertRaises(ShiftHistoryGuardError):
            append_shift_event(
                self.event(seq=2), registry_path=self.path,
                installation_id=INSTALLATION, runtime_id=RUNTIME,
            )

    def test_wrong_predecessor_fails_closed(self):
        self.append()
        with self.assertRaises(ShiftHistoryGuardError):
            append_shift_event(
                self.event(previous=evidence(999)), registry_path=self.path,
                installation_id=INSTALLATION, runtime_id=RUNTIME,
            )

    def test_exact_replay_is_duplicate_no_op(self):
        raw = self.event()
        first = append_shift_event(raw, registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME)
        replay = append_shift_event(raw, registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME)
        self.assertEqual(first.status, "ACCEPTED")
        self.assertEqual(replay.status, "DUPLICATE_NO_OP")
        self.assertEqual(replay.accepted_count, 1)

    def test_same_id_different_binding_is_identity_conflict(self):
        raw = self.event(event_id="same")
        first = append_shift_event(raw, registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME)
        self.assertEqual(first.status, "ACCEPTED")
        changed = {**raw, "to_gear": "G4"}
        with self.assertRaisesRegex(ShiftHistoryGuardError, "IDENTITY_CONFLICT"):
            append_shift_event(changed, registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME)

    def test_same_evidence_new_id_is_lineage_duplicate(self):
        first = self.append(event_id="e1", evidence_n=77)
        replay = append_shift_event(
            self.event(event_id="e2", evidence_n=77),
            registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME,
        )
        self.assertEqual(first.status, "ACCEPTED")
        self.assertEqual(replay.status, "LINEAGE_DUPLICATE_NO_OP")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["events"]), 1)

    def test_cross_restart_registry_preserves_exactly_once(self):
        raw = self.event(event_id="restart-e1")
        first = append_shift_event(raw, registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME)
        self.assertEqual(first.status, "ACCEPTED")
        replay = append_shift_event(raw, registry_path=Path(str(self.path)), installation_id=INSTALLATION, runtime_id=RUNTIME)
        self.assertEqual(replay.status, "DUPLICATE_NO_OP")

    def test_reload_rejects_tampered_event_payload(self):
        self.append()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["events"][0]["to_gear"] = "G6"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ShiftHistoryGuardError):
            evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)

    def test_reload_rejects_tampered_identity_index(self):
        self.append()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["by_event_id"]["shift-1"] = evidence(999)
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ShiftHistoryGuardError):
            evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)

    def test_reload_rejects_tampered_head_or_latest_seq(self):
        self.append()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["head_hash"] = evidence(998)
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ShiftHistoryGuardError):
            evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)

    def test_cross_runtime_and_installation_are_rejected(self):
        self.append()
        with self.assertRaises(ShiftHistoryGuardError):
            append_shift_event(
                self.event(installation="other"), registry_path=self.path,
                installation_id=INSTALLATION, runtime_id=RUNTIME,
            )
        with self.assertRaises(ShiftHistoryGuardError):
            evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id="other", policy=POLICY)

    def test_event_identity_and_scope_are_typed(self):
        bad_ids = (None, 1, True, [], {}, "bad id")
        for bad in bad_ids:
            with self.subTest(value=bad):
                raw = self.event()
                raw["event_id"] = bad
                with self.assertRaises(ShiftHistoryGuardError):
                    append_shift_event(raw, registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME)

    def test_small_n_cannot_enter_thrash(self):
        for _ in range(4):
            self.append()
        obs = evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)
        self.assertFalse(obs.sufficient_support)
        self.assertEqual(obs.state_after, "CLEAR")
        self.assertEqual(obs.transition, "INSUFFICIENT_SUPPORT")

    def test_uncertainty_bound_required_for_enter(self):
        # 3/5 raw rate is 0.60, but its Wilson lower bound is far below 0.50.
        for i in range(5):
            if i < 3:
                self.append(from_gear="G2", to_gear="G3")
            else:
                self.append(from_gear="G3", to_gear="G3")
        obs = evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)
        self.assertEqual(obs.shift_rate, 0.6)
        self.assertLess(obs.wilson_lower, POLICY["enter_rate"])
        self.assertEqual(obs.state_after, "CLEAR")
        self.assertEqual(obs.transition, "HOLD")

    def test_all_shifts_can_enter_after_support(self):
        for _ in range(5):
            self.append()
        obs = evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)
        self.assertTrue(obs.sufficient_support)
        self.assertGreaterEqual(obs.wilson_lower, POLICY["enter_rate"])
        self.assertEqual(obs.state_after, "THRASH")
        self.assertEqual(obs.transition, "ENTER")

    def test_stateful_exit_uses_lower_threshold_and_upper_bound(self):
        for _ in range(5):
            self.append()
        entered = evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)
        self.assertEqual(entered.state_after, "THRASH")
        for _ in range(5):
            self.append(from_gear="G3", to_gear="G3")
        exited = evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)
        self.assertLessEqual(exited.wilson_upper, POLICY["exit_rate"])
        self.assertEqual(exited.state_after, "CLEAR")
        self.assertEqual(exited.transition, "EXIT")

    def test_middle_region_holds_existing_state(self):
        for _ in range(5):
            self.append()
        evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)
        pattern = [True, True, True, False, False]
        for changed in pattern:
            self.append(from_gear="G2", to_gear="G3" if changed else "G2")
        held = evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)
        self.assertEqual(held.state_before, "THRASH")
        self.assertEqual(held.state_after, "THRASH")
        self.assertEqual(held.transition, "HOLD")

    def test_policy_change_cannot_silently_clear_active_guard(self):
        for _ in range(5):
            self.append()
        evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)
        for _ in range(5):
            self.append(from_gear="G3", to_gear="G3")
        changed_policy = {**POLICY, "exit_rate": 0.49, "z_value": 1.0}
        obs = evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=changed_policy)
        self.assertEqual(obs.state_after, "THRASH")
        self.assertEqual(obs.transition, "POLICY_CHANGED_HOLD")

    def test_invalid_policy_fails_closed(self):
        bad_policies = [
            {**POLICY, "minimum_support": 6},
            {**POLICY, "exit_rate": 0.5},
            {**POLICY, "window_size": 0},
            {**POLICY, "z_value": 0},
        ]
        for bad in bad_policies:
            with self.subTest(policy=bad):
                with self.assertRaises(ShiftHistoryGuardError):
                    evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=bad)

    def test_observation_has_no_live_or_formal_authority_and_no_credit(self):
        for _ in range(5):
            self.append()
        obs = evaluate_thrash(registry_path=self.path, installation_id=INSTALLATION, runtime_id=RUNTIME, policy=POLICY)
        self.assertFalse(obs.live_routing_authority_allowed)
        self.assertFalse(obs.formal_mutation_allowed)
        self.assertEqual(obs.experience_delta, 0)
        self.assertEqual(obs.operational_progress_delta, 0)


if __name__ == "__main__":
    unittest.main()
