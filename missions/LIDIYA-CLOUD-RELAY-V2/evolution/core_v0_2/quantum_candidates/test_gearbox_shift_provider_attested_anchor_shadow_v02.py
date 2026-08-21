import json
import os
import tempfile
import unittest
from pathlib import Path

from gearbox_shift_durability_anchor_shadow_v01 import (
    DurabilityAnchorGuardError,
    ZERO_HASH,
    _ledger_snapshot,
    append_shift_event_anchored,
    initialize_empty_anchor,
)
from gearbox_shift_anchor_trust_recovery_shadow_v01 import PROVIDER_DOMAIN_ID
from gearbox_shift_provider_attested_anchor_shadow_v02 import (
    ProviderAttestationGuardError,
    attest_current_anchor,
    attest_recovery_audit,
    initialize_provider_state,
    provider_shadow_boundaries,
    reconcile_attestation_journal_from_provider_state,
    verify_provider_attested_anchor,
    verify_recovery_audit_attested,
)

INSTALL = "install-A"
RUNTIME = "runtime-A"
SECRET = b"quantum-shadow-provider-key-v01-32bytes-minimum"


def event(seq: int, previous: str) -> dict:
    return {
        "event_id": f"shift-{seq}",
        "seq": seq,
        "from_gear": "G2",
        "to_gear": "G3",
        "evidence_sha256": f"{seq:064x}"[-64:],
        "previous_event_hash": previous,
        "installation_id": INSTALL,
        "runtime_id": RUNTIME,
    }


class ProviderAttestedAnchorShadowV02Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.registry = root / "ledger" / "shift.json"
        self.anchor = root / "anchor" / "anchor.json"
        self.shift_lock = root / "locks" / "shift.lock"
        self.provider_lock = root / "locks" / "provider.lock"
        self.provider_state = root / "provider" / "state.json"
        self.journal = root / "provider" / "anchor-journal.json"
        self.recovery_registry = root / "recovery" / "receipts.json"
        initialize_empty_anchor(
            registry_path=self.registry,
            anchor_path=self.anchor,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        )
        initialize_provider_state(
            provider_state_path=self.provider_state,
            provider_secret=SECRET,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
        )
        self.first_attestation = self.attest_anchor()

    def tearDown(self):
        self.tmp.cleanup()

    def attest_anchor(self):
        return attest_current_anchor(
            registry_path=self.registry,
            anchor_path=self.anchor,
            provider_state_path=self.provider_state,
            attestation_journal_path=self.journal,
            provider_lock_path=self.provider_lock,
            provider_secret=SECRET,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
        )

    def append_one(self):
        seq, head = _ledger_snapshot(
            self.registry, installation_id=INSTALL, runtime_id=RUNTIME
        )
        result = append_shift_event_anchored(
            event(seq + 1, head if seq else ZERO_HASH),
            registry_path=self.registry,
            anchor_path=self.anchor,
            lock_path=self.shift_lock,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
            durability_domain_id=PROVIDER_DOMAIN_ID,
        )
        self.assertEqual(result.status, "ACCEPTED_ANCHORED")
        return result

    def write_recovery_registry(self, receipts=None):
        self.recovery_registry.parent.mkdir(parents=True, exist_ok=True)
        self.recovery_registry.write_text(
            json.dumps({"schema_version": "0.1-shadow", "receipts": receipts or {}},
                       sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_normal_anchor_chain_is_provider_attested(self):
        self.assertEqual(
            verify_provider_attested_anchor(
                registry_path=self.registry,
                anchor_path=self.anchor,
                provider_state_path=self.provider_state,
                attestation_journal_path=self.journal,
                provider_secret=SECRET,
                installation_id=INSTALL,
                runtime_id=RUNTIME,
            ),
            "PROVIDER_ATTESTED_ANCHOR_MATCH",
        )
        self.append_one()
        second = self.attest_anchor()
        self.assertEqual(second.provider_seq, self.first_attestation.provider_seq + 1)
        self.assertEqual(second.previous_attestation_hash, self.first_attestation.attestation_hash())

    def test_consumer_journal_rollback_is_detected_by_provider_floor(self):
        journal_at_first = self.journal.read_text(encoding="utf-8")
        self.append_one()
        self.attest_anchor()
        self.journal.write_text(journal_at_first, encoding="utf-8")
        with self.assertRaisesRegex(ProviderAttestationGuardError, "MONOTONIC_FLOOR_MISMATCH"):
            verify_provider_attested_anchor(
                registry_path=self.registry,
                anchor_path=self.anchor,
                provider_state_path=self.provider_state,
                attestation_journal_path=self.journal,
                provider_secret=SECRET,
                installation_id=INSTALL,
                runtime_id=RUNTIME,
            )

    def test_exact_one_missing_journal_receipt_can_reconcile_from_provider_state(self):
        journal_at_first = self.journal.read_text(encoding="utf-8")
        self.append_one()
        self.attest_anchor()
        self.journal.write_text(journal_at_first, encoding="utf-8")
        result = reconcile_attestation_journal_from_provider_state(
            provider_state_path=self.provider_state,
            attestation_journal_path=self.journal,
            provider_lock_path=self.provider_lock,
            provider_secret=SECRET,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
        )
        self.assertEqual(result, "JOURNAL_RECONCILED_FROM_PROVIDER_STATE")
        self.assertEqual(
            verify_provider_attested_anchor(
                registry_path=self.registry,
                anchor_path=self.anchor,
                provider_state_path=self.provider_state,
                attestation_journal_path=self.journal,
                provider_secret=SECRET,
                installation_id=INSTALL,
                runtime_id=RUNTIME,
            ),
            "PROVIDER_ATTESTED_ANCHOR_MATCH",
        )

    def test_more_than_one_journal_receipt_rollback_fails_closed(self):
        journal_at_first = self.journal.read_text(encoding="utf-8")
        self.append_one()
        self.attest_anchor()
        self.append_one()
        self.attest_anchor()
        self.journal.write_text(journal_at_first, encoding="utf-8")
        with self.assertRaisesRegex(ProviderAttestationGuardError, "exceeds one recoverable"):
            reconcile_attestation_journal_from_provider_state(
                provider_state_path=self.provider_state,
                attestation_journal_path=self.journal,
                provider_lock_path=self.provider_lock,
                provider_secret=SECRET,
                installation_id=INSTALL,
                runtime_id=RUNTIME,
            )

    def test_recovery_audit_registry_rollback_is_detected(self):
        self.write_recovery_registry({"r1": "hash-1"})
        attest_recovery_audit(
            recovery_registry_path=self.recovery_registry,
            provider_state_path=self.provider_state,
            provider_lock_path=self.provider_lock,
            provider_secret=SECRET,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
        )
        old = self.recovery_registry.read_text(encoding="utf-8")
        self.write_recovery_registry({"r1": "hash-1", "r2": "hash-2"})
        attest_recovery_audit(
            recovery_registry_path=self.recovery_registry,
            provider_state_path=self.provider_state,
            provider_lock_path=self.provider_lock,
            provider_secret=SECRET,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
        )
        self.recovery_registry.write_text(old, encoding="utf-8")
        with self.assertRaisesRegex(ProviderAttestationGuardError, "ROLLBACK_OR_TAMPER"):
            verify_recovery_audit_attested(
                recovery_registry_path=self.recovery_registry,
                provider_state_path=self.provider_state,
                provider_secret=SECRET,
                installation_id=INSTALL,
                runtime_id=RUNTIME,
            )

    def test_recovery_audit_must_be_rebound_after_anchor_advances(self):
        self.write_recovery_registry({"r1": "hash-1"})
        attest_recovery_audit(
            recovery_registry_path=self.recovery_registry,
            provider_state_path=self.provider_state,
            provider_lock_path=self.provider_lock,
            provider_secret=SECRET,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
        )
        self.append_one()
        self.attest_anchor()
        with self.assertRaisesRegex(ProviderAttestationGuardError, "stale anchor attestation"):
            verify_recovery_audit_attested(
                recovery_registry_path=self.recovery_registry,
                provider_state_path=self.provider_state,
                provider_secret=SECRET,
                installation_id=INSTALL,
                runtime_id=RUNTIME,
            )

    def test_provider_state_mutations_share_one_lock(self):
        self.write_recovery_registry({"r1": "hash-1"})
        os.mkdir(self.provider_lock)
        try:
            with self.assertRaisesRegex(DurabilityAnchorGuardError, "WRITER_LOCK_HELD"):
                attest_recovery_audit(
                    recovery_registry_path=self.recovery_registry,
                    provider_state_path=self.provider_state,
                    provider_lock_path=self.provider_lock,
                    provider_secret=SECRET,
                    installation_id=INSTALL,
                    runtime_id=RUNTIME,
                )
        finally:
            os.rmdir(self.provider_lock)

    def test_shadow_boundaries_remain_non_authoritative(self):
        boundaries = provider_shadow_boundaries()
        self.assertFalse(boundaries["formal_mutation_allowed"])
        self.assertFalse(boundaries["live_routing_authority_allowed"])
        self.assertEqual(boundaries["experience_delta"], 0)
        self.assertEqual(boundaries["operational_progress_delta"], 0)
        self.assertFalse(boundaries["production_external_provider_proven"])
        self.assertFalse(boundaries["provider_state_rollback_resistance_proven"])


if __name__ == "__main__":
    unittest.main()
