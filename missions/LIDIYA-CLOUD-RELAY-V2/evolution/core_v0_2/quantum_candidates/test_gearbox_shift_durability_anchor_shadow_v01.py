import json
import os
import tempfile
import unittest
from pathlib import Path

from gearbox_shift_history_shadow_v01 import append_shift_event
from gearbox_shift_durability_anchor_shadow_v01 import (
    DurabilityAnchorGuardError,
    append_shift_event_anchored,
    exclusive_writer_lock,
    initialize_empty_anchor,
    verify_anchor,
)

INSTALL = "install-A"
RUNTIME = "runtime-A"
DOMAIN = "trusted-anchor-domain-A"
ZERO = "0" * 64


def event(seq: int, previous: str, *, event_id: str | None = None, evidence: str | None = None,
          from_gear: str = "G2", to_gear: str = "G3") -> dict:
    return {
        "event_id": event_id or f"shift-{seq}",
        "seq": seq,
        "from_gear": from_gear,
        "to_gear": to_gear,
        "evidence_sha256": evidence or (f"{seq:064x}"[-64:]),
        "previous_event_hash": previous,
        "installation_id": INSTALL,
        "runtime_id": RUNTIME,
    }


class ShiftDurabilityAnchorShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.root = root
        self.registry = root / "ledger" / "shift.json"
        self.anchor = root / "anchor-domain" / "anchor.json"
        self.lock = root / "locks" / "shift.lock"

    def tearDown(self):
        self.tmp.cleanup()

    def init_anchor(self):
        return initialize_empty_anchor(
            registry_path=self.registry,
            anchor_path=self.anchor,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
            durability_domain_id=DOMAIN,
        )

    def append1(self):
        return append_shift_event_anchored(
            event(1, ZERO),
            registry_path=self.registry,
            anchor_path=self.anchor,
            lock_path=self.lock,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
            durability_domain_id=DOMAIN,
        )

    def test_empty_bootstrap_is_exactly_zero(self):
        receipt = self.init_anchor()
        self.assertEqual(receipt.anchor_seq, 0)
        self.assertEqual(receipt.ledger_head_hash, ZERO)
        verified = verify_anchor(
            registry_path=self.registry, anchor_path=self.anchor,
            installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id=DOMAIN,
        )
        self.assertEqual(verified.status, "ANCHOR_MATCH")
        self.assertFalse(verified.live_routing_authority_allowed)
        self.assertFalse(verified.formal_mutation_allowed)
        self.assertEqual(verified.experience_delta, 0)
        self.assertEqual(verified.operational_progress_delta, 0)

    def test_nonempty_ledger_cannot_be_retroactively_bootstrapped(self):
        append_shift_event(event(1, ZERO), registry_path=self.registry, installation_id=INSTALL, runtime_id=RUNTIME)
        with self.assertRaises(DurabilityAnchorGuardError):
            self.init_anchor()

    def test_anchored_append_advances_ledger_and_anchor_together(self):
        self.init_anchor()
        result = self.append1()
        self.assertEqual(result.status, "ACCEPTED_ANCHORED")
        self.assertEqual(result.ledger_seq, 1)
        self.assertEqual(result.anchor_seq, 1)
        self.assertEqual(result.anchor_status, "ANCHOR_MATCH")

    def test_duplicate_append_is_noop_and_anchor_does_not_advance(self):
        self.init_anchor()
        first = self.append1()
        second = append_shift_event_anchored(
            event(1, ZERO), registry_path=self.registry, anchor_path=self.anchor, lock_path=self.lock,
            installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id=DOMAIN,
        )
        self.assertEqual(second.status, "NO_OP_ANCHOR_UNCHANGED")
        self.assertEqual(second.event_status, "DUPLICATE_NO_OP")
        self.assertEqual(second.anchor_seq, first.anchor_seq)
        self.assertEqual(second.anchor_hash, first.anchor_hash)

    def test_whole_ledger_rollback_to_older_valid_snapshot_is_detected(self):
        self.init_anchor()
        first = self.append1()
        old_bytes = self.registry.read_bytes()
        second_event = event(2, first.ledger_head_hash)
        append_shift_event_anchored(
            second_event, registry_path=self.registry, anchor_path=self.anchor, lock_path=self.lock,
            installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id=DOMAIN,
        )
        self.registry.write_bytes(old_bytes)
        status = verify_anchor(
            registry_path=self.registry, anchor_path=self.anchor,
            installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id=DOMAIN,
        )
        self.assertEqual(status.status, "LEDGER_ROLLBACK_DETECTED")

    def test_equal_sequence_internally_valid_fork_is_detected(self):
        self.init_anchor()
        self.append1()
        alternate = self.root / "alternate" / "shift.json"
        append_shift_event(
            event(1, ZERO, event_id="fork-1", evidence="f" * 64),
            registry_path=alternate, installation_id=INSTALL, runtime_id=RUNTIME,
        )
        self.registry.write_bytes(alternate.read_bytes())
        status = verify_anchor(
            registry_path=self.registry, anchor_path=self.anchor,
            installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id=DOMAIN,
        )
        self.assertEqual(status.status, "LEDGER_ANCHOR_FORK_DETECTED")

    def test_internal_event_tamper_fails_before_anchor_comparison(self):
        self.init_anchor()
        self.append1()
        data = json.loads(self.registry.read_text(encoding="utf-8"))
        data["events"][0]["to_gear"] = "G4"
        self.registry.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(DurabilityAnchorGuardError, "shift registry integrity failure"):
            verify_anchor(
                registry_path=self.registry, anchor_path=self.anchor,
                installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id=DOMAIN,
            )

    def test_unanchored_ledger_advance_fails_closed(self):
        self.init_anchor()
        direct = append_shift_event(event(1, ZERO), registry_path=self.registry, installation_id=INSTALL, runtime_id=RUNTIME)
        self.assertEqual(direct.status, "ACCEPTED")
        status = verify_anchor(
            registry_path=self.registry, anchor_path=self.anchor,
            installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id=DOMAIN,
        )
        self.assertEqual(status.status, "UNANCHORED_LEDGER_ADVANCE")
        with self.assertRaisesRegex(DurabilityAnchorGuardError, "UNANCHORED_LEDGER_ADVANCE"):
            append_shift_event_anchored(
                event(2, direct.head_hash), registry_path=self.registry, anchor_path=self.anchor, lock_path=self.lock,
                installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id=DOMAIN,
            )

    def test_anchor_hash_tamper_fails_closed(self):
        self.init_anchor()
        data = json.loads(self.anchor.read_text(encoding="utf-8"))
        data["anchor_hash"] = "f" * 64
        self.anchor.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(DurabilityAnchorGuardError, "anchor hash mismatch"):
            verify_anchor(
                registry_path=self.registry, anchor_path=self.anchor,
                installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id=DOMAIN,
            )

    def test_cross_domain_anchor_rejected(self):
        self.init_anchor()
        with self.assertRaisesRegex(DurabilityAnchorGuardError, "durability domain mismatch"):
            verify_anchor(
                registry_path=self.registry, anchor_path=self.anchor,
                installation_id=INSTALL, runtime_id=RUNTIME, durability_domain_id="other-domain",
            )

    def test_writer_lock_creates_parent_and_blocks_second_writer(self):
        self.assertFalse(self.lock.parent.exists())
        with exclusive_writer_lock(self.lock, owner_token="writer-a"):
            self.assertTrue(self.lock.exists())
            with self.assertRaisesRegex(DurabilityAnchorGuardError, "WRITER_LOCK_HELD"):
                with exclusive_writer_lock(self.lock, owner_token="writer-b"):
                    pass
        self.assertFalse(self.lock.exists())

    def test_preexisting_abandoned_lock_is_fail_closed(self):
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        os.mkdir(self.lock)
        (self.lock / "owner.json").write_text(json.dumps({"owner_token": "dead-writer"}), encoding="utf-8")
        with self.assertRaisesRegex(DurabilityAnchorGuardError, "WRITER_LOCK_HELD"):
            with exclusive_writer_lock(self.lock, owner_token="new-writer"):
                pass

    def test_anchor_previous_hash_links_successive_anchor_states(self):
        initial = self.init_anchor()
        self.append1()
        data = json.loads(self.anchor.read_text(encoding="utf-8"))
        self.assertEqual(data["previous_anchor_hash"], initial.anchor_hash())


if __name__ == "__main__":
    unittest.main()
