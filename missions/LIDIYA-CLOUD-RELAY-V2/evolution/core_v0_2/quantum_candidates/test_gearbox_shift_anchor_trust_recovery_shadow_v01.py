import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from gearbox_shift_history_shadow_v01 import append_shift_event
from gearbox_shift_durability_anchor_shadow_v01 import (
    ZERO_HASH,
    _ledger_snapshot,
    _load_anchor,
    initialize_empty_anchor,
    verify_anchor,
)
from gearbox_shift_anchor_trust_recovery_shadow_v01 import (
    AnchorRecoveryGuardError,
    PROVIDER_DOMAIN_ID,
    RecoveryResult,
    recover_unanchored_advance,
    sign_recovery_receipt,
    verify_recovery_receipt,
)

INSTALL = "install-A"
RUNTIME = "runtime-A"
SECRET = b"quantum-shadow-provider-key-v01-32bytes-minimum"
BAD_SECRET = b"wrong-shadow-provider-key-material-0000000000"


def event(seq: int, previous: str, *, event_id: str | None = None, evidence: str | None = None) -> dict:
    return {
        "event_id": event_id or f"shift-{seq}",
        "seq": seq,
        "from_gear": "G2",
        "to_gear": "G3",
        "evidence_sha256": evidence or (f"{seq:064x}"[-64:]),
        "previous_event_hash": previous,
        "installation_id": INSTALL,
        "runtime_id": RUNTIME,
    }


class ShiftAnchorTrustRecoveryShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.registry = root / "ledger" / "shift.json"
        self.anchor = root / "anchor" / "anchor.json"
        self.lock = root / "locks" / "shift.lock"
        self.recovery_registry = root / "recovery" / "receipts.json"
        initialize_empty_anchor(
            registry_path=self.registry, anchor_path=self.anchor,
            installation_id=INSTALL, runtime_id=RUNTIME,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def make_one_step_crash(self):
        anchor = _load_anchor(
            self.anchor, installation_id=INSTALL, runtime_id=RUNTIME,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        )
        appended = append_shift_event(
            event(1, ZERO_HASH), registry_path=self.registry,
            installation_id=INSTALL, runtime_id=RUNTIME,
        )
        self.assertEqual(appended.status, "ACCEPTED")
        ledger_seq, ledger_head = _ledger_snapshot(
            self.registry, installation_id=INSTALL, runtime_id=RUNTIME,
        )
        self.assertEqual(verify_anchor(
            registry_path=self.registry, anchor_path=self.anchor,
            installation_id=INSTALL, runtime_id=RUNTIME,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        ).status, "UNANCHORED_LEDGER_ADVANCE")
        unsigned = {
            "recovery_id": "recovery-1",
            "previous_anchor_hash": anchor.anchor_hash(),
            "observed_anchor_seq": anchor.anchor_seq,
            "observed_anchor_head_hash": anchor.ledger_head_hash,
            "observed_ledger_seq": ledger_seq,
            "observed_ledger_head_hash": ledger_head,
            "installation_id": INSTALL,
            "runtime_id": RUNTIME,
            "nonce": "nonce-1",
        }
        return sign_recovery_receipt(unsigned, provider_secret=SECRET)

    def recover(self, receipt) -> RecoveryResult:
        return recover_unanchored_advance(
            receipt=receipt, provider_secret=SECRET,
            registry_path=self.registry, anchor_path=self.anchor,
            lock_path=self.lock, recovery_registry_path=self.recovery_registry,
            installation_id=INSTALL, runtime_id=RUNTIME,
        )

    def test_authenticated_one_step_crash_recovery_advances_anchor(self):
        receipt = self.make_one_step_crash()
        result = self.recover(receipt)
        self.assertEqual(result.status, "RECOVERY_APPLIED")
        self.assertEqual(result.ledger_seq, 1)
        self.assertEqual(result.anchor_seq, 1)
        self.assertFalse(result.live_routing_authority_allowed)
        self.assertFalse(result.formal_mutation_allowed)
        self.assertEqual(result.experience_delta, 0)
        self.assertEqual(result.operational_progress_delta, 0)
        self.assertEqual(verify_anchor(
            registry_path=self.registry, anchor_path=self.anchor,
            installation_id=INSTALL, runtime_id=RUNTIME,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        ).status, "ANCHOR_MATCH")

    def test_wrong_provider_secret_is_rejected(self):
        receipt = self.make_one_step_crash()
        with self.assertRaisesRegex(AnchorRecoveryGuardError, "fingerprint mismatch"):
            verify_recovery_receipt(receipt, provider_secret=BAD_SECRET)

    def test_authenticated_receipt_tamper_is_rejected(self):
        receipt = self.make_one_step_crash()
        data = asdict(receipt)
        data["observed_ledger_head_hash"] = "f" * 64
        with self.assertRaisesRegex(AnchorRecoveryGuardError, "authentication failed"):
            self.recover(data)

    def test_receipt_scope_mismatch_is_rejected(self):
        receipt = self.make_one_step_crash()
        with self.assertRaisesRegex(AnchorRecoveryGuardError, "scope mismatch"):
            recover_unanchored_advance(
                receipt=receipt, provider_secret=SECRET,
                registry_path=self.registry, anchor_path=self.anchor,
                lock_path=self.lock, recovery_registry_path=self.recovery_registry,
                installation_id=INSTALL, runtime_id="other-runtime",
            )

    def test_more_than_one_unanchored_advance_cannot_be_blessed(self):
        receipt = self.make_one_step_crash()
        seq, head = _ledger_snapshot(self.registry, installation_id=INSTALL, runtime_id=RUNTIME)
        self.assertEqual(seq, 1)
        append_shift_event(
            event(2, head), registry_path=self.registry,
            installation_id=INSTALL, runtime_id=RUNTIME,
        )
        with self.assertRaisesRegex(AnchorRecoveryGuardError, "exactly one"):
            self.recover(receipt)

    def test_recovery_receipt_replay_is_idempotent(self):
        receipt = self.make_one_step_crash()
        first = self.recover(receipt)
        second = self.recover(receipt)
        self.assertEqual(first.status, "RECOVERY_APPLIED")
        self.assertEqual(second.status, "RECOVERY_ALREADY_APPLIED_NO_OP")
        self.assertEqual(first.anchor_seq, second.anchor_seq)

    def test_same_recovery_id_different_authenticated_binding_is_conflict(self):
        receipt = self.make_one_step_crash()
        self.recover(receipt)
        altered = dict(receipt.unsigned_binding())
        altered["nonce"] = "nonce-2"
        altered_receipt = sign_recovery_receipt(altered, provider_secret=SECRET)
        with self.assertRaisesRegex(AnchorRecoveryGuardError, "RECOVERY_IDENTITY_CONFLICT"):
            self.recover(altered_receipt)

    def test_anchor_match_without_matching_recovery_binding_is_not_blessed(self):
        receipt = self.make_one_step_crash()
        self.recover(receipt)
        other = dict(receipt.unsigned_binding())
        other["recovery_id"] = "recovery-2"
        other["previous_anchor_hash"] = "f" * 64
        other_receipt = sign_recovery_receipt(other, provider_secret=SECRET)
        with self.assertRaisesRegex(AnchorRecoveryGuardError, "does not match current anchored state"):
            self.recover(other_receipt)


if __name__ == "__main__":
    unittest.main()
