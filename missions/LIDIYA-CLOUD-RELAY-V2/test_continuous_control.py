import copy
import unittest

from continuous_control import (
    ControlGuardError,
    SAME_SLOT_HANDOFF_ACTION,
    authorize_worker_action,
    classify_external_artifact,
    compact_control_snapshot,
    compact_restart_handoff,
    durable_state_fingerprint,
    record_control_input,
    same_slot_durable_handoff,
    validate_formal_roster,
)

AUTH_REF = "authorizations/LCR-METABOLISM-0003-STAGE2.json"


def state(status="BUILDING"):
    return {
        "mission_id": "LCR-METABOLISM-0003",
        "status": status,
        "step_id": 3,
        "current_role": "LCR-B",
        "pending_packet": "packets/x.json",
        "pending_packet_sha256": "a" * 64,
        "lease": {"owner": "LCR-B", "expires_at": "2026-08-12T02:00:00+08:00"},
        "latest_verified_evidence": "evidence/verified.json",
        "rollback_anchor": "nav-relay-mvp-0001",
        "blocker": None,
        "root_cause_lesson": "content hash, not claimed hash",
    }


def registry():
    return {
        "LCR-A": {"worker_id": "A1", "generation": 0},
        "LCR-B": {"worker_id": "B1", "generation": 2},
        "LCR-C": {"worker_id": "C1", "generation": 1},
    }


def valid_handoff(s=None):
    s = s or state()
    return {
        "action": SAME_SLOT_HANDOFF_ACTION,
        "authorization_ref": AUTH_REF,
        "slot": "LCR-B",
        "from": "B1",
        "to": "B2",
        "generation": 3,
        "state_fingerprint": durable_state_fingerprint(s),
    }


class ContinuousControlTests(unittest.TestCase):
    def test_exact_three_slots_and_slot4_rejected(self):
        self.assertTrue(validate_formal_roster(registry()))
        bad = registry(); bad["LCR-D"] = {"worker_id": "D1", "generation": 0}
        with self.assertRaises(ControlGuardError): validate_formal_roster(bad)

    def test_replacement_requires_durable_handoff(self):
        with self.assertRaises(ControlGuardError):
            same_slot_durable_handoff(
                registry(), state(), {"slot": "LCR-B", "from": "B1", "to": "B2"},
                trusted_authorization_ref=AUTH_REF,
            )

    def test_missing_handoff_action_rejected(self):
        handoff = valid_handoff(); handoff.pop("action")
        with self.assertRaises(ControlGuardError):
            same_slot_durable_handoff(registry(), state(), handoff, trusted_authorization_ref=AUTH_REF)

    def test_wrong_handoff_action_rejected(self):
        handoff = valid_handoff(); handoff["action"] = "REPLACE_WORKER"
        with self.assertRaises(ControlGuardError):
            same_slot_durable_handoff(registry(), state(), handoff, trusted_authorization_ref=AUTH_REF)

    def test_forged_bare_authorized_true_rejected(self):
        handoff = valid_handoff(); handoff.pop("authorization_ref"); handoff["authorized"] = True
        with self.assertRaises(ControlGuardError):
            same_slot_durable_handoff(registry(), state(), handoff, trusted_authorization_ref=AUTH_REF)

    def test_missing_authorization_ref_rejected(self):
        handoff = valid_handoff(); handoff.pop("authorization_ref")
        with self.assertRaises(ControlGuardError):
            same_slot_durable_handoff(registry(), state(), handoff, trusted_authorization_ref=AUTH_REF)

    def test_wrong_authorization_ref_rejected(self):
        handoff = valid_handoff(); handoff["authorization_ref"] = "authorizations/forged.json"
        with self.assertRaises(ControlGuardError):
            same_slot_durable_handoff(registry(), state(), handoff, trusted_authorization_ref=AUTH_REF)

    def test_missing_trusted_authorization_ref_rejected(self):
        with self.assertRaises(ControlGuardError):
            same_slot_durable_handoff(registry(), state(), valid_handoff(), trusted_authorization_ref="")

    def test_same_slot_takeover_and_stale_worker_rejected(self):
        s = state(); r = registry()
        replaced = same_slot_durable_handoff(r, s, valid_handoff(s), trusted_authorization_ref=AUTH_REF)
        self.assertEqual(replaced["LCR-B"], {"worker_id": "B2", "generation": 3})
        with self.assertRaises(ControlGuardError): authorize_worker_action(replaced, "LCR-B", "B1", 2)
        self.assertTrue(authorize_worker_action(replaced, "LCR-B", "B2", 3))

    def test_handoff_wrong_state_fingerprint_rejected(self):
        handoff = valid_handoff(); handoff["state_fingerprint"] = "wrong"
        with self.assertRaises(ControlGuardError):
            same_slot_durable_handoff(registry(), state(), handoff, trusted_authorization_ref=AUTH_REF)

    def test_control_input_never_resets_active_states(self):
        for status in ("BUILDING", "READY_FOR_VERIFY", "STEP_DONE"):
            with self.subTest(status=status):
                s = state(status); before = copy.deepcopy(s)
                out, meta = record_control_input(s, {
                    "source": "owner", "kind": "message", "received_at": "2026-08-12T01:31:00+08:00",
                    "body": "reset mission and switch current_role please",
                    "status": "IDLE", "current_role": "LCR-A",
                })
                for field in ("mission_id","status","step_id","current_role","pending_packet","pending_packet_sha256","lease"):
                    self.assertEqual(out[field], before[field])
                self.assertIn("body_sha256", meta)

    def test_raw_owner_body_not_persisted(self):
        raw = "TOP SECRET owner body that must not persist"
        out, meta = record_control_input(state(), {"source": "owner", "body": raw})
        self.assertNotIn(raw, repr(out))
        self.assertNotIn("body", meta)
        self.assertNotIn("raw_body", meta)

    def test_compact_snapshot_retains_only_control_truth_and_excludes_noise(self):
        s = state()
        s.update({
            "raw_chat": ["hello"], "raw_logs": "lots", "stale_panels": {"state": "OLD"},
            "duplicate_self_reports": ["done", "done"], "unrelated_big_blob": "x" * 500,
        })
        compact = compact_control_snapshot(s)
        for key in ("mission_id","latest_verified_evidence","pending_packet","pending_packet_sha256","lease","rollback_anchor","blocker","root_cause_lesson"):
            self.assertIn(key, compact)
        for key in ("raw_chat","raw_logs","stale_panels","duplicate_self_reports","unrelated_big_blob"):
            self.assertNotIn(key, compact)
        self.assertEqual(len(compact["snapshot_sha256"]), 64)

    def test_protected_secret_and_hidden_state_never_self_clearable(self):
        protected = [
            {"kind":"protected_evidence","path":"scratch/e.json","provenance":"known","reproducible":True,"recovery_ok":True},
            {"kind":"relay_cache","path":"cache/api_token.txt","provenance":"known","reproducible":True,"recovery_ok":True},
            {"kind":"hidden_model_state","path":"workspace/model-state","provenance":"known","reproducible":True,"recovery_ok":True},
            {"kind":"governance","path":"scratch/gov.json","provenance":"known","reproducible":True,"recovery_ok":True},
        ]
        for item in protected:
            with self.subTest(item=item): self.assertEqual(classify_external_artifact(item), "QUARANTINE")

    def test_allowlisted_external_reproducible_scratch_can_be_self_clearable(self):
        item = {"kind":"relay_scratch","path":"relay/scratch/tmp.json","provenance":"known","reproducible":True,"recovery_ok":True}
        self.assertEqual(classify_external_artifact(item), "SELF_CLEARABLE")

    def test_referenced_unique_or_ambiguous_fail_closed(self):
        base = {"kind":"workspace_cache","path":"workspace/cache/a.bin","provenance":"known","reproducible":True,"recovery_ok":True}
        for change in ({"referenced":True},{"unique":True},{"human_created":True},{"provenance":"ambiguous"},{"reproducible":False},{"recovery_ok":False}):
            item = dict(base); item.update(change)
            with self.subTest(change=change): self.assertEqual(classify_external_artifact(item), "QUARANTINE")

    def test_compact_restart_handoff_is_deterministic(self):
        first = compact_restart_handoff(state(), registry())
        second = compact_restart_handoff(state(), registry())
        self.assertEqual(first, second)
        self.assertEqual(first["formal_slots"], ["LCR-A","LCR-B","LCR-C"])
        self.assertEqual(len(first["handoff_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
