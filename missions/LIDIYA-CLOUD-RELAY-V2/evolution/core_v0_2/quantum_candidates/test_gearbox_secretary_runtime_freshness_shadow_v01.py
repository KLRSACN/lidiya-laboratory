import unittest
from dataclasses import asdict

from gearbox_secretary_signal_shadow_v01 import PINNED_SECRETARY_PROTOCOL_BLOB_SHA
from gearbox_secretary_runtime_freshness_shadow_v01 import (
    SecretaryFreshnessGuardError,
    project_secretary_with_runtime_clock_shadow,
    sign_runtime_clock,
    sign_secretary_observation,
)

INSTALL = "install-A"
RUNTIME = "runtime-A"
CLOCK_SECRET = b"quantum-runtime-clock-shadow-key-v01-32bytes"
SECRETARY_SECRET = b"quantum-w07-secretary-shadow-key-v01-32bytes"
ZERO = "0" * 64


def envelope(*, issued=10, valid=20, level="ORANGE"):
    return {
        "schema_version":"1.0-shadow","mission_id":"LCR-EVOLUTION-0005","step_id":9,
        "source_role":"W07","authority":"NONE","protocol_blob_sha":PINNED_SECRETARY_PROTOCOL_BLOB_SHA,
        "signal_id":"sig-1","installation_id":INSTALL,"runtime_id":RUNTIME,
        "issued_seq":issued,"valid_through_seq":valid,"secretary_level":level,
        "measurements":{
            "context_load_ratio":{"value":0.8,"source_role":"W07","sensor_id":"ctx","observed_seq":issued,"valid_through_seq":valid,"installation_id":INSTALL,"runtime_id":RUNTIME},
            "tool_failure_ratio":{"value":0.6,"source_role":"W07","sensor_id":"tool","observed_seq":issued,"valid_through_seq":valid,"installation_id":INSTALL,"runtime_id":RUNTIME},
        },
    }


def clock(seq=15, previous=ZERO, runtime=RUNTIME):
    return sign_runtime_clock({
        "clock_seq":seq,"previous_clock_hash":previous,"installation_id":INSTALL,
        "runtime_id":runtime,"nonce":f"n-{seq}"
    }, clock_secret=CLOCK_SECRET)


class SecretaryRuntimeFreshnessShadowTests(unittest.TestCase):
    def project(self, env, clk, signed=None, **extra):
        signed = signed or sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        return project_secretary_with_runtime_clock_shadow(
            env, signed_observation=signed, clock_receipt=clk,
            clock_secret=CLOCK_SECRET, secretary_secret=SECRETARY_SECRET,
            expected_previous_clock_hash=ZERO, minimum_clock_seq=0,
            installation_id=INSTALL, runtime_id=RUNTIME, **extra)

    def test_authenticated_clock_enables_shadow_routing_projection(self):
        env = envelope()
        d = self.project(env, clock())
        self.assertTrue(d.routing_authority_allowed)
        self.assertEqual(d.routing_secretary_level, "ORANGE")
        self.assertEqual(d.routing_pressure_inputs["context_load_ratio"], 0.8)
        self.assertEqual(d.verified_experience_delta, 0)
        self.assertFalse(d.formal_mutation_allowed)

    def test_stale_clock_neutralizes_signal(self):
        env = envelope()
        d = self.project(env, clock(seq=21))
        self.assertFalse(d.routing_authority_allowed)
        self.assertEqual(d.routing_secretary_level, "UNKNOWN")
        self.assertIn("STALE_ENVELOPE", d.status)

    def test_future_envelope_neutralized(self):
        env = envelope(issued=20, valid=30)
        d = self.project(env, clock(seq=15))
        self.assertFalse(d.routing_authority_allowed)
        self.assertIn("FUTURE_ENVELOPE", d.status)

    def test_authority_conflict_always_zero_effect(self):
        env = envelope()
        d = self.project(env, clock(), authority_conflict=True)
        self.assertFalse(d.routing_authority_allowed)
        self.assertEqual(d.routing_secretary_level, "UNKNOWN")

    def test_signed_signal_tamper_rejected(self):
        env = envelope()
        signed = asdict(sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET))
        signed["signal_fingerprint"] = "f" * 64
        with self.assertRaisesRegex(SecretaryFreshnessGuardError, "binding mismatch"):
            self.project(env, clock(), signed=signed)

    def test_clock_mac_tamper_rejected(self):
        env = envelope()
        clk = asdict(clock())
        clk["clock_seq"] = 16
        with self.assertRaisesRegex(SecretaryFreshnessGuardError, "authentication failed"):
            self.project(env, clk)

    def test_clock_replay_floor_rejected(self):
        env = envelope()
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        with self.assertRaisesRegex(SecretaryFreshnessGuardError, "replay/non-monotonic"):
            project_secretary_with_runtime_clock_shadow(
                env, signed_observation=signed, clock_receipt=clock(seq=15),
                clock_secret=CLOCK_SECRET, secretary_secret=SECRETARY_SECRET,
                expected_previous_clock_hash=ZERO, minimum_clock_seq=15,
                installation_id=INSTALL, runtime_id=RUNTIME)

    def test_wrong_clock_predecessor_rejected(self):
        env = envelope()
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        with self.assertRaisesRegex(SecretaryFreshnessGuardError, "predecessor mismatch"):
            project_secretary_with_runtime_clock_shadow(
                env, signed_observation=signed, clock_receipt=clock(seq=15),
                clock_secret=CLOCK_SECRET, secretary_secret=SECRETARY_SECRET,
                expected_previous_clock_hash="f" * 64, minimum_clock_seq=0,
                installation_id=INSTALL, runtime_id=RUNTIME)

    def test_cross_runtime_clock_rejected(self):
        env = envelope()
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        other = clock(seq=15, runtime="runtime-B")
        with self.assertRaisesRegex(SecretaryFreshnessGuardError, "scope mismatch"):
            project_secretary_with_runtime_clock_shadow(
                env, signed_observation=signed, clock_receipt=other,
                clock_secret=CLOCK_SECRET, secretary_secret=SECRETARY_SECRET,
                expected_previous_clock_hash=ZERO, minimum_clock_seq=0,
                installation_id=INSTALL, runtime_id=RUNTIME)

    def test_partial_field_freshness_is_per_field(self):
        env = envelope()
        env["measurements"]["tool_failure_ratio"]["valid_through_seq"] = 14
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        d = self.project(env, clock(seq=15), signed=signed)
        self.assertTrue(d.routing_authority_allowed)
        self.assertIn("context_load_ratio", d.accepted_fields)
        self.assertIn("tool_failure_ratio", d.dropped_fields)
        self.assertEqual(d.routing_pressure_inputs["tool_failure_ratio"], 0.0)

    def test_no_fresh_fields_cannot_enable_routing(self):
        env = envelope()
        for m in env["measurements"].values():
            m["valid_through_seq"] = 14
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        d = self.project(env, clock(seq=15), signed=signed)
        self.assertFalse(d.routing_authority_allowed)
        self.assertEqual(d.routing_secretary_level, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
