import unittest
from dataclasses import asdict

from gearbox_secretary_signal_shadow_v01 import PINNED_SECRETARY_PROTOCOL_BLOB_SHA
from gearbox_secretary_runtime_freshness_shadow_v01 import (
    SecretaryFreshnessGuardError,
    sign_runtime_clock,
    sign_secretary_observation,
)
from gearbox_secretary_runtime_freshness_shadow_v02 import (
    ZERO_HASH,
    advance_clock_checkpoint,
    project_secretary_with_authenticated_checkpoint_shadow,
    sign_clock_checkpoint,
)

INSTALL = "install-A"
RUNTIME = "runtime-A"
CLOCK_SECRET = b"quantum-runtime-clock-shadow-key-v01-32bytes"
SECRETARY_SECRET = b"quantum-w07-secretary-shadow-key-v01-32bytes"


def envelope():
    return {
        "schema_version":"1.0-shadow","mission_id":"LCR-EVOLUTION-0005","step_id":9,
        "source_role":"W07","authority":"NONE","protocol_blob_sha":PINNED_SECRETARY_PROTOCOL_BLOB_SHA,
        "signal_id":"sig-1","installation_id":INSTALL,"runtime_id":RUNTIME,
        "issued_seq":10,"valid_through_seq":20,"secretary_level":"YELLOW",
        "measurements":{
            "context_load_ratio":{"value":0.7,"source_role":"W07","sensor_id":"ctx","observed_seq":10,"valid_through_seq":20,"installation_id":INSTALL,"runtime_id":RUNTIME}
        },
    }


def checkpoint(seq=0, last_hash=ZERO_HASH, nonce="cp-0"):
    return sign_clock_checkpoint({
        "last_clock_seq":seq,"last_clock_hash":last_hash,
        "installation_id":INSTALL,"runtime_id":RUNTIME,"checkpoint_nonce":nonce,
    }, clock_secret=CLOCK_SECRET)


def clock(seq=15, previous=ZERO_HASH):
    return sign_runtime_clock({
        "clock_seq":seq,"previous_clock_hash":previous,
        "installation_id":INSTALL,"runtime_id":RUNTIME,"nonce":f"clock-{seq}",
    }, clock_secret=CLOCK_SECRET)


class SecretaryRuntimeFreshnessShadowV02Tests(unittest.TestCase):
    def test_authenticated_checkpoint_allows_fresh_projection(self):
        env = envelope()
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        d = project_secretary_with_authenticated_checkpoint_shadow(
            env, signed_observation=signed, clock_receipt=clock(), clock_checkpoint=checkpoint(),
            clock_secret=CLOCK_SECRET, secretary_secret=SECRETARY_SECRET,
            installation_id=INSTALL, runtime_id=RUNTIME)
        self.assertTrue(d.routing_authority_allowed)
        self.assertEqual(d.routing_secretary_level, "YELLOW")
        self.assertEqual(d.verified_experience_delta, 0)
        self.assertFalse(d.formal_mutation_allowed)

    def test_forged_lower_checkpoint_rejected_by_authentication(self):
        cp = asdict(checkpoint(seq=12, last_hash="a" * 64, nonce="cp-12"))
        cp["last_clock_seq"] = 0
        cp["last_clock_hash"] = ZERO_HASH
        env = envelope()
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        with self.assertRaisesRegex(SecretaryFreshnessGuardError, "checkpoint authentication failed"):
            project_secretary_with_authenticated_checkpoint_shadow(
                env, signed_observation=signed, clock_receipt=clock(), clock_checkpoint=cp,
                clock_secret=CLOCK_SECRET, secretary_secret=SECRETARY_SECRET,
                installation_id=INSTALL, runtime_id=RUNTIME)

    def test_receipt_must_chain_from_checkpoint(self):
        cp = checkpoint(seq=12, last_hash="a" * 64, nonce="cp-12")
        env = envelope()
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        with self.assertRaisesRegex(SecretaryFreshnessGuardError, "predecessor mismatch"):
            project_secretary_with_authenticated_checkpoint_shadow(
                env, signed_observation=signed, clock_receipt=clock(seq=15, previous=ZERO_HASH), clock_checkpoint=cp,
                clock_secret=CLOCK_SECRET, secretary_secret=SECRETARY_SECRET,
                installation_id=INSTALL, runtime_id=RUNTIME)

    def test_replayed_clock_at_checkpoint_floor_rejected(self):
        prior = clock(seq=15, previous=ZERO_HASH)
        cp = checkpoint(seq=15, last_hash=prior.receipt_hash(), nonce="cp-15")
        replay = sign_runtime_clock({
            "clock_seq":15,"previous_clock_hash":prior.receipt_hash(),
            "installation_id":INSTALL,"runtime_id":RUNTIME,"nonce":"clock-replay",
        }, clock_secret=CLOCK_SECRET)
        env = envelope()
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        with self.assertRaisesRegex(SecretaryFreshnessGuardError, "replay/non-monotonic"):
            project_secretary_with_authenticated_checkpoint_shadow(
                env, signed_observation=signed, clock_receipt=replay, clock_checkpoint=cp,
                clock_secret=CLOCK_SECRET, secretary_secret=SECRETARY_SECRET,
                installation_id=INSTALL, runtime_id=RUNTIME)

    def test_checkpoint_advance_binds_exact_verified_receipt_hash(self):
        cp0 = checkpoint()
        r1 = clock(seq=11, previous=ZERO_HASH)
        cp1 = advance_clock_checkpoint(
            cp0, r1, clock_secret=CLOCK_SECRET,
            installation_id=INSTALL, runtime_id=RUNTIME, checkpoint_nonce="cp-11")
        self.assertEqual(cp1.last_clock_seq, 11)
        self.assertEqual(cp1.last_clock_hash, r1.receipt_hash())

    def test_checkpoint_scope_is_bound(self):
        cp = asdict(checkpoint())
        cp["runtime_id"] = "runtime-B"
        env = envelope()
        signed = sign_secretary_observation(env, secretary_secret=SECRETARY_SECRET)
        with self.assertRaises(SecretaryFreshnessGuardError):
            project_secretary_with_authenticated_checkpoint_shadow(
                env, signed_observation=signed, clock_receipt=clock(), clock_checkpoint=cp,
                clock_secret=CLOCK_SECRET, secretary_secret=SECRETARY_SECRET,
                installation_id=INSTALL, runtime_id=RUNTIME)


if __name__ == "__main__":
    unittest.main()
