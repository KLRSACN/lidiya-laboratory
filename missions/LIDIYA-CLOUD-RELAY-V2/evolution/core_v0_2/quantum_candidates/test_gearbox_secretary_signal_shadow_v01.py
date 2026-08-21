import unittest

from gearbox_controller import GearboxGuardError
from gearbox_secretary_signal_shadow_v01 import (
    NEUTRAL_PRESSURE,
    PINNED_SECRETARY_PROTOCOL_BLOB_SHA,
    PRESSURE_FIELDS,
    project_secretary_signal_shadow,
)


def measurement(value, *, seq=10, through=12, sensor="sensor-a", installation="install-a", runtime="runtime-a"):
    return {
        "value": value,
        "source_role": "W07",
        "sensor_id": sensor,
        "observed_seq": seq,
        "valid_through_seq": through,
        "installation_id": installation,
        "runtime_id": runtime,
    }


def envelope(*, issued=10, through=12, level="ORANGE", measurements=None,
             protocol_sha=PINNED_SECRETARY_PROTOCOL_BLOB_SHA,
             installation="install-a", runtime="runtime-a", step_id=9,
             source_role="W07", authority="NONE"):
    if measurements is None:
        measurements = {
            "context_load_ratio": measurement(0.7, installation=installation, runtime=runtime),
            "tool_failure_ratio": measurement(0.2, installation=installation, runtime=runtime),
            "stale_pointer_ratio": measurement(0.3, installation=installation, runtime=runtime),
            "durable_progress_age_ratio": measurement(0.4, installation=installation, runtime=runtime),
            "continuity_anchor_health": measurement(0.8, installation=installation, runtime=runtime),
            "storage_pressure_ratio": measurement(0.5, installation=installation, runtime=runtime),
        }
    return {
        "schema_version": "1.0-shadow",
        "mission_id": "LCR-EVOLUTION-0005",
        "step_id": step_id,
        "source_role": source_role,
        "authority": authority,
        "protocol_blob_sha": protocol_sha,
        "signal_id": "sig-001",
        "installation_id": installation,
        "runtime_id": runtime,
        "issued_seq": issued,
        "valid_through_seq": through,
        "secretary_level": level,
        "measurements": measurements,
    }


class SecretarySignalShadowTests(unittest.TestCase):
    def test_fresh_fields_are_sanitized_but_observational_only(self):
        p = project_secretary_signal_shadow(envelope(), trusted_current_seq=11)
        self.assertEqual(set(p.accepted_fields), PRESSURE_FIELDS)
        self.assertFalse(p.routing_authority_allowed)
        self.assertFalse(p.formal_mutation_allowed)
        self.assertEqual(p.verified_experience_delta, 0)
        self.assertEqual(p.operational_progress_delta, 0)
        self.assertEqual(p.status, "FRESH_FIELDS_OBSERVATIONAL_ONLY")

    def test_stale_envelope_has_zero_effect(self):
        p = project_secretary_signal_shadow(envelope(issued=5, through=9), trusted_current_seq=10)
        self.assertEqual(p.secretary_level, "UNKNOWN")
        self.assertEqual(p.pressure_inputs, NEUTRAL_PRESSURE)
        self.assertEqual(p.status, "STALE_ENVELOPE_ZERO_EFFECT")

    def test_future_envelope_has_zero_effect(self):
        p = project_secretary_signal_shadow(envelope(issued=12, through=14), trusted_current_seq=11)
        self.assertEqual(p.pressure_inputs, NEUTRAL_PRESSURE)
        self.assertEqual(p.status, "FUTURE_ENVELOPE_ZERO_EFFECT")

    def test_authority_conflict_zeroes_all_secretary_effect(self):
        p = project_secretary_signal_shadow(envelope(), trusted_current_seq=11, authority_conflict=True)
        self.assertEqual(p.secretary_level, "UNKNOWN")
        self.assertEqual(p.pressure_inputs, NEUTRAL_PRESSURE)
        self.assertEqual(p.status, "AUTHORITY_CONFLICT_ZERO_EFFECT")

    def test_stale_single_field_is_neutralized_without_poisoning_fresh_fields(self):
        fields = envelope()["measurements"]
        fields["tool_failure_ratio"] = measurement(0.9, seq=5, through=9)
        p = project_secretary_signal_shadow(envelope(measurements=fields), trusted_current_seq=11)
        self.assertIn("tool_failure_ratio", p.dropped_fields)
        self.assertNotIn("tool_failure_ratio", p.accepted_fields)
        self.assertEqual(p.pressure_inputs["tool_failure_ratio"], 0.0)
        self.assertEqual(p.pressure_inputs["context_load_ratio"], 0.7)

    def test_future_single_field_is_neutralized(self):
        fields = envelope()["measurements"]
        fields["stale_pointer_ratio"] = measurement(0.9, seq=12, through=12)
        p = project_secretary_signal_shadow(envelope(measurements=fields), trusted_current_seq=11)
        self.assertEqual(p.pressure_inputs["stale_pointer_ratio"], 0.0)
        self.assertIn("stale_pointer_ratio", p.dropped_fields)

    def test_missing_field_uses_safe_neutral_default(self):
        fields = envelope()["measurements"]
        fields.pop("continuity_anchor_health")
        p = project_secretary_signal_shadow(envelope(measurements=fields), trusted_current_seq=11)
        self.assertEqual(p.pressure_inputs["continuity_anchor_health"], 1.0)
        self.assertIn("continuity_anchor_health", p.dropped_fields)

    def test_mixed_installation_provenance_fails_closed(self):
        fields = envelope()["measurements"]
        fields["tool_failure_ratio"] = measurement(0.9, installation="other-install")
        with self.assertRaises(GearboxGuardError):
            project_secretary_signal_shadow(envelope(measurements=fields), trusted_current_seq=11)

    def test_mixed_runtime_provenance_fails_closed(self):
        fields = envelope()["measurements"]
        fields["tool_failure_ratio"] = measurement(0.9, runtime="other-runtime")
        with self.assertRaises(GearboxGuardError):
            project_secretary_signal_shadow(envelope(measurements=fields), trusted_current_seq=11)

    def test_field_validity_cannot_outlive_envelope(self):
        fields = envelope()["measurements"]
        fields["tool_failure_ratio"] = measurement(0.9, through=13)
        with self.assertRaises(GearboxGuardError):
            project_secretary_signal_shadow(envelope(measurements=fields), trusted_current_seq=11)

    def test_protocol_snapshot_mismatch_requires_rebase(self):
        bad_sha = "0" * 40
        with self.assertRaises(GearboxGuardError):
            project_secretary_signal_shadow(envelope(protocol_sha=bad_sha), trusted_current_seq=11)

    def test_source_role_cannot_be_promoted_to_authority(self):
        with self.assertRaises(GearboxGuardError):
            project_secretary_signal_shadow(envelope(authority="ROUTING"), trusted_current_seq=11)
        with self.assertRaises(GearboxGuardError):
            project_secretary_signal_shadow(envelope(source_role="LCR-A"), trusted_current_seq=11)

    def test_cross_step_requires_rebase(self):
        with self.assertRaises(GearboxGuardError):
            project_secretary_signal_shadow(envelope(step_id=10), trusted_current_seq=11)

    def test_bool_or_out_of_range_measurement_fails_closed(self):
        for bad in (True, -0.1, 1.1, "0.5"):
            fields = envelope()["measurements"]
            fields["context_load_ratio"] = measurement(bad)
            with self.subTest(value=bad):
                with self.assertRaises(GearboxGuardError):
                    project_secretary_signal_shadow(envelope(measurements=fields), trusted_current_seq=11)

    def test_unknown_pressure_field_fails_closed(self):
        fields = envelope()["measurements"]
        fields["mystery_pressure"] = measurement(0.9)
        with self.assertRaises(GearboxGuardError):
            project_secretary_signal_shadow(envelope(measurements=fields), trusted_current_seq=11)

    def test_invalid_current_seq_fails_closed(self):
        for bad in (-1, True, 1.5, "11"):
            with self.subTest(value=bad):
                with self.assertRaises(GearboxGuardError):
                    project_secretary_signal_shadow(envelope(), trusted_current_seq=bad)

    def test_envelope_fingerprint_changes_on_measurement_change(self):
        p1 = project_secretary_signal_shadow(envelope(), trusted_current_seq=11)
        fields = envelope()["measurements"]
        fields["context_load_ratio"] = measurement(0.71)
        p2 = project_secretary_signal_shadow(envelope(measurements=fields), trusted_current_seq=11)
        self.assertNotEqual(p1.envelope_fingerprint, p2.envelope_fingerprint)


if __name__ == "__main__":
    unittest.main()
