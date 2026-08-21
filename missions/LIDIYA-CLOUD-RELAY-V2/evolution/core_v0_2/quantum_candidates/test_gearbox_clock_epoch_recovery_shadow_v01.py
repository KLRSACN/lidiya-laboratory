import hashlib
import json
import unittest
from dataclasses import asdict

from gearbox_authority_experience_signer_shadow_v01 import SCHEMA as SIGNER_SCHEMA, sign_for_regression
from gearbox_clock_epoch_recovery_shadow_v01 import (
    ClockEpochRecoveryGuardError,
    advance_epoch_checkpoint,
    bootstrap_clock_epoch_from_signer_root,
    initial_epoch_checkpoint,
    open_recovery_gate,
    project_fresh_secretary_after_recovery,
    recover_clock_epoch,
    recovery_dataflow_boundaries,
    sign_clock_epoch_snapshot_for_regression,
    sign_epoch_bound_secretary_observation,
    sign_epoch_clock,
    verify_epoch_clock,
)
from gearbox_external_monotonic_provider_shadow_v01 import MonotonicReceipt, ProviderBinding
from gearbox_secretary_runtime_freshness_shadow_v01 import SECRETARY_KEY_SHA256
from gearbox_secretary_signal_shadow_v01 import PINNED_SECRETARY_PROTOCOL_BLOB_SHA
from gearbox_signer_epoch_recovery_shadow_v01 import bootstrap_trust_root, recover_new_epoch

MISSION_BLOB = "e32e01fa304a857f5185951443682ea937335473"
INSTALL = "inst-A"
RUNTIME = "run-A"
LOCAL_DOMAIN = "local-domain"
SECRETARY_SECRET = b"quantum-w07-secretary-shadow-key-v01-32bytes"


def canon_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def trust1():
    x = {
        "schema_version": SIGNER_SCHEMA,
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "snapshot_id": "trust-1",
        "authority_active_epoch": "a-epoch-1",
        "verifier_active_epochs": {"LCR-C": "c-epoch-1"},
        "revoked_epochs": [],
        "previous_snapshot_sha256": "0" * 64,
    }
    x["signature"] = sign_for_regression(x, "LCR-A", "a-epoch-1")
    return x


def trust2(previous):
    x = {
        "schema_version": SIGNER_SCHEMA,
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "snapshot_id": "trust-2",
        "authority_active_epoch": "a-epoch-2",
        "verifier_active_epochs": {"LCR-C": "c-epoch-2"},
        "revoked_epochs": ["a-epoch-1", "c-epoch-1"],
        "previous_snapshot_sha256": canon_hash(previous),
    }
    x["signature"] = sign_for_regression(x, "LCR-A", "a-epoch-2")
    return x


def clock_snapshot1(signer_trust):
    return sign_clock_epoch_snapshot_for_regression({
        "snapshot_id": "clock-trust-1",
        "clock_epoch_id": "clock-epoch-1",
        "previous_clock_epoch_sha256": "0" * 64,
        "revoked_clock_epochs": [],
    }, signer_trust)


def clock_snapshot2(previous_clock, signer_trust):
    return sign_clock_epoch_snapshot_for_regression({
        "snapshot_id": "clock-trust-2",
        "clock_epoch_id": "clock-epoch-2",
        "previous_clock_epoch_sha256": canon_hash(asdict(previous_clock)),
        "revoked_clock_epochs": ["clock-epoch-1"],
    }, signer_trust)


def fresh_authority(signer_trust, selected_state="G3"):
    env = {
        "schema_version": "1.0-shadow",
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "authority_role": "LCR-A",
        "mission_state_blob_sha": MISSION_BLOB,
        "decision_id": "clock-recovery-fresh-authority",
        "selected_state": selected_state,
        "guard_status": "CLEAR",
        "return_condition": "downshift on verified risk",
        "checkpoint_required": True,
        "receiver_ack_required": True,
        "verification_gate": "NOT_PROMOTION_EVIDENCE",
        "formal_mutation_allowed": False,
    }
    x = {
        "envelope": env,
        "signer_role": "LCR-A",
        "key_epoch": signer_trust["authority_active_epoch"],
        "trust_snapshot_id": signer_trust["snapshot_id"],
    }
    x["signature"] = sign_for_regression(x, "LCR-A", signer_trust["authority_active_epoch"])
    return x


def envelope(signal_id="fresh-sig", issued=10, valid=20, level="YELLOW"):
    return {
        "schema_version": "1.0-shadow",
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": 9,
        "source_role": "W07",
        "authority": "NONE",
        "protocol_blob_sha": PINNED_SECRETARY_PROTOCOL_BLOB_SHA,
        "signal_id": signal_id,
        "installation_id": INSTALL,
        "runtime_id": RUNTIME,
        "issued_seq": issued,
        "valid_through_seq": valid,
        "secretary_level": level,
        "measurements": {
            "context_load_ratio": {
                "value": 0.7,
                "source_role": "W07",
                "sensor_id": "ctx",
                "observed_seq": issued,
                "valid_through_seq": valid,
                "installation_id": INSTALL,
                "runtime_id": RUNTIME,
            }
        },
    }


class FakeExternalProvider:
    def __init__(self, domain="remote-trust-domain"):
        self._binding = ProviderBinding("provider-A", domain, INSTALL, RUNTIME)
        self.floor = 0
        self.last_receipt_hash = "GENESIS"

    def binding(self):
        return self._binding

    def read_floor(self):
        return self.floor

    def issue(self, *, expected_previous_sequence, previous_receipt_hash, payload_hash):
        if expected_previous_sequence != self.floor:
            raise ValueError("provider expected sequence mismatch")
        if previous_receipt_hash != self.last_receipt_hash:
            raise ValueError("provider predecessor mismatch")
        self.floor += 1
        receipt_hash = hashlib.sha256(f"{self.floor}|{previous_receipt_hash}|{payload_hash}".encode()).hexdigest()
        self.last_receipt_hash = receipt_hash
        return MonotonicReceipt(
            "provider-A", self._binding.durability_domain_id,
            self._binding.installation_id, self._binding.runtime_id,
            self.floor, previous_receipt_hash, payload_hash, receipt_hash, "valid",
        )

    def verify(self, receipt):
        return receipt.signature == "valid"


class ClockEpochRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(hashlib.sha256(SECRETARY_SECRET).hexdigest(), SECRETARY_KEY_SHA256)
        self.provider = FakeExternalProvider()
        self.signer_old = trust1()
        signer_root_old = bootstrap_trust_root(
            trust_snapshot=self.signer_old,
            provider=self.provider,
            installation_id=INSTALL,
            runtime_id=RUNTIME,
            local_durability_domain_id=LOCAL_DOMAIN,
        )
        self.signer_new = trust2(self.signer_old)
        self.signer_root = recover_new_epoch(
            current_root=signer_root_old,
            replacement_trust_snapshot=self.signer_new,
            provider=self.provider,
            fresh_mission_state_blob_sha=MISSION_BLOB,
        )
        self.clock1 = clock_snapshot1(self.signer_new)
        self.clock_root1 = bootstrap_clock_epoch_from_signer_root(
            signer_root=self.signer_root,
            clock_snapshot=asdict(self.clock1),
            provider=self.provider,
            fresh_mission_state_blob_sha=MISSION_BLOB,
        )

    def recover(self):
        clock2 = clock_snapshot2(self.clock1, self.signer_new)
        root2 = recover_clock_epoch(
            current_root=self.clock_root1,
            replacement_clock_snapshot=asdict(clock2),
            provider=self.provider,
            fresh_mission_state_blob_sha=MISSION_BLOB,
        )
        return clock2, root2

    def test_chain_break_fails_closed_then_authenticated_new_epoch_reenters_neutral(self):
        cp1 = initial_epoch_checkpoint(self.clock_root1)
        bad = sign_epoch_clock(
            clock_root=self.clock_root1,
            checkpoint=cp1,
            provider=self.provider,
            clock_seq=11,
            nonce="old-clock-11",
        )
        forged = asdict(bad)
        forged["previous_clock_hash"] = "f" * 64
        with self.assertRaises(ClockEpochRecoveryGuardError):
            verify_epoch_clock(
                forged, checkpoint=cp1, clock_root=self.clock_root1, provider=self.provider,
            )

        _, root2 = self.recover()
        gate = open_recovery_gate(
            clock_root=root2,
            provider=self.provider,
            signed_authority=fresh_authority(self.signer_new),
        )
        self.assertEqual(gate.state, "CLOCK_RECOVERY_FRESH_AUTHORITY_READY_SHADOW")
        self.assertEqual(gate.selected_state, "G3")
        self.assertEqual(gate.secretary_level, "UNKNOWN")
        self.assertTrue(all(value == 0.0 for value in gate.pressure_inputs.values()))
        self.assertFalse(gate.pressure_history_consumed)
        self.assertFalse(gate.stale_pressure_carryover_allowed)
        self.assertFalse(gate.terminal_hold_carryover_allowed)
        self.assertEqual(gate.experience_delta, 0)

    def test_old_clock_checkpoint_and_old_epoch_pressure_cannot_cross_recovery(self):
        cp1 = initial_epoch_checkpoint(self.clock_root1)
        old_env = envelope(signal_id="old-pressure")
        old_obs = sign_epoch_bound_secretary_observation(
            old_env, clock_root=self.clock_root1, secretary_secret=SECRETARY_SECRET,
        )
        _, root2 = self.recover()
        gate = open_recovery_gate(
            clock_root=root2, provider=self.provider,
            signed_authority=fresh_authority(self.signer_new),
        )
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError, "epoch/schema mismatch"):
            verify_epoch_clock(
                {"clock_epoch_id": "clock-epoch-1", "clock_seq": 15,
                 "previous_clock_hash": cp1.last_clock_hash,
                 "installation_id": INSTALL, "runtime_id": RUNTIME,
                 "nonce": "old", "mac_sha256": "0" * 64,
                 "schema_version": "1.0-shadow"},
                checkpoint=cp1, clock_root=root2, provider=self.provider,
            )
        cp2 = initial_epoch_checkpoint(root2)
        r2 = sign_epoch_clock(
            clock_root=root2, checkpoint=cp2, provider=self.provider,
            clock_seq=15, nonce="new-clock-15",
        )
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError, "previous clock epoch"):
            project_fresh_secretary_after_recovery(
                gate=gate, clock_root=root2, provider=self.provider,
                envelope_value=old_env, epoch_observation=old_obs,
                checkpoint=cp2, clock_receipt=r2,
                secretary_secret=SECRETARY_SECRET,
            )

    def test_only_fresh_current_epoch_pressure_can_route_after_recovery(self):
        _, root2 = self.recover()
        gate = open_recovery_gate(
            clock_root=root2, provider=self.provider,
            signed_authority=fresh_authority(self.signer_new),
        )
        cp2 = initial_epoch_checkpoint(root2)
        r2 = sign_epoch_clock(
            clock_root=root2, checkpoint=cp2, provider=self.provider,
            clock_seq=15, nonce="clock-15",
        )
        env = envelope()
        obs = sign_epoch_bound_secretary_observation(
            env, clock_root=root2, secretary_secret=SECRETARY_SECRET,
        )
        projection = project_fresh_secretary_after_recovery(
            gate=gate, clock_root=root2, provider=self.provider,
            envelope_value=env, epoch_observation=obs,
            checkpoint=cp2, clock_receipt=r2,
            secretary_secret=SECRETARY_SECRET,
        )
        self.assertTrue(projection.routing_authority_allowed)
        self.assertEqual(projection.routing_secretary_level, "YELLOW")
        self.assertEqual(projection.verified_experience_delta, 0)
        self.assertEqual(projection.operational_progress_delta, 0)
        self.assertFalse(projection.formal_mutation_allowed)

    def test_clock_checkpoint_advances_only_from_current_epoch_receipt(self):
        _, root2 = self.recover()
        cp2 = initial_epoch_checkpoint(root2)
        r2 = sign_epoch_clock(
            clock_root=root2, checkpoint=cp2, provider=self.provider,
            clock_seq=7, nonce="clock-7",
        )
        cp3 = advance_epoch_checkpoint(
            clock_root=root2, checkpoint=cp2, clock_receipt=r2,
            provider=self.provider, nonce="cp-7",
        )
        self.assertEqual(cp3.clock_epoch_id, "clock-epoch-2")
        self.assertEqual(cp3.last_clock_seq, 7)
        self.assertEqual(cp3.last_clock_hash, r2.receipt_hash())

    def test_old_clock_root_rollback_is_detected_by_external_floor(self):
        self.recover()
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError, "ROLLBACK_OR_FLOOR_DIVERGENCE"):
            initial = initial_epoch_checkpoint(self.clock_root1)
            verify_epoch_clock(
                sign_epoch_clock(
                    clock_root=self.clock_root1, checkpoint=initial,
                    provider=self.provider, clock_seq=5, nonce="rollback-attempt",
                ),
                checkpoint=initial, clock_root=self.clock_root1, provider=self.provider,
            )

    def test_replacement_must_revoke_old_clock_epoch(self):
        bad = sign_clock_epoch_snapshot_for_regression({
            "snapshot_id": "clock-trust-2-bad",
            "clock_epoch_id": "clock-epoch-2",
            "previous_clock_epoch_sha256": canon_hash(asdict(self.clock1)),
            "revoked_clock_epochs": [],
        }, self.signer_new)
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError, "OLD_CLOCK_EPOCH_NOT_REVOKED"):
            recover_clock_epoch(
                current_root=self.clock_root1,
                replacement_clock_snapshot=asdict(bad),
                provider=self.provider,
                fresh_mission_state_blob_sha=MISSION_BLOB,
            )

    def test_fresh_mission_blob_change_blocks_clock_recovery(self):
        clock2 = clock_snapshot2(self.clock1, self.signer_new)
        with self.assertRaisesRegex(ClockEpochRecoveryGuardError, "Mission authority changed"):
            recover_clock_epoch(
                current_root=self.clock_root1,
                replacement_clock_snapshot=asdict(clock2),
                provider=self.provider,
                fresh_mission_state_blob_sha="a" * 40,
            )

    def test_authority_conflict_zeroes_fresh_pressure_after_recovery(self):
        _, root2 = self.recover()
        gate = open_recovery_gate(
            clock_root=root2, provider=self.provider,
            signed_authority=fresh_authority(self.signer_new),
        )
        cp2 = initial_epoch_checkpoint(root2)
        r2 = sign_epoch_clock(
            clock_root=root2, checkpoint=cp2, provider=self.provider,
            clock_seq=15, nonce="clock-conflict",
        )
        env = envelope()
        obs = sign_epoch_bound_secretary_observation(env, clock_root=root2, secretary_secret=SECRETARY_SECRET)
        projection = project_fresh_secretary_after_recovery(
            gate=gate, clock_root=root2, provider=self.provider,
            envelope_value=env, epoch_observation=obs,
            checkpoint=cp2, clock_receipt=r2,
            secretary_secret=SECRETARY_SECRET,
            authority_conflict=True,
        )
        self.assertFalse(projection.routing_authority_allowed)
        self.assertEqual(projection.routing_secretary_level, "NONE")
        self.assertTrue(all(v == 0.0 for v in projection.routing_pressure_inputs.values()))
        self.assertEqual(projection.verified_experience_delta, 0)

    def test_recovery_metadata_is_excluded_from_learning_personality_and_appraisal(self):
        b = recovery_dataflow_boundaries()
        self.assertFalse(b["recovery_counts_as_experience"])
        self.assertFalse(b["recovery_counts_as_operational_progress"])
        self.assertFalse(b["pressure_history_consumed"])
        self.assertFalse(b["stale_pressure_carryover_allowed"])
        self.assertFalse(b["terminal_hold_carryover_allowed"])
        self.assertFalse(b["secretary_clock_metadata_counts_as_experience"])
        self.assertFalse(b["secretary_clock_metadata_counts_as_personality"])
        self.assertFalse(b["secretary_clock_metadata_counts_as_appraisal_reward"])
        self.assertFalse(b["secretary_clock_metadata_counts_as_trauma_or_relief"])
        self.assertFalse(b["p_base_mutation_allowed"])
        self.assertFalse(b["real_external_provider_installed"])
        self.assertFalse(b["production_clock_key_protection_proven"])


if __name__ == "__main__":
    unittest.main()
