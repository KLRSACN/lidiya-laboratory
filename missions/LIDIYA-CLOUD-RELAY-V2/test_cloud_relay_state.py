from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from cloud_relay_state import (
    RelayStateError,
    claim,
    clear_lease,
    consume_once,
    packet,
    retry_step,
    transition,
)

UTC = timezone.utc


def base_state(status: str = "IDLE") -> dict:
    return {
        "schema_version": "2.0",
        "mission_id": "LCR-ROUNDTRIP-0001",
        "status": status,
        "step_id": 1,
        "attempt": 0,
        "current_role": "LCR-A",
        "next_role": "LCR-A",
        "candidate_ref": "lidiya-cloud-relay-v2",
        "last_packet_sha256": None,
        "lease": None,
    }


class TransitionTests(unittest.TestCase):
    def test_happy_path_roles(self):
        state = base_state()
        state = transition(state, "COORDINATING")
        self.assertEqual(state["current_role"], "LCR-A")
        state = transition(state, "READY_FOR_BUILDER")
        self.assertEqual(state["current_role"], "LCR-B")
        state = transition(state, "BUILDING")
        state = transition(state, "READY_FOR_VERIFY")
        self.assertEqual(state["current_role"], "LCR-C")
        state = transition(state, "VERIFYING")
        state = transition(state, "STEP_DONE")
        self.assertEqual(state["current_role"], "LCR-A")

    def test_invalid_transition_is_rejected(self):
        with self.assertRaises(RelayStateError):
            transition(base_state(), "VERIFYING")


class LeaseTests(unittest.TestCase):
    def test_active_lease_blocks_second_worker(self):
        at = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        state = base_state("READY_FOR_BUILDER")
        state = claim(state, "LCR-B", "builder-1", ttl_seconds=60, at=at)
        with self.assertRaises(RelayStateError):
            claim(state, "LCR-B", "builder-2", ttl_seconds=60, at=at + timedelta(seconds=10))

    def test_expired_lease_can_be_reclaimed(self):
        at = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        state = base_state("READY_FOR_BUILDER")
        state = claim(state, "LCR-B", "builder-1", ttl_seconds=60, at=at)
        state = claim(state, "LCR-B", "builder-2", ttl_seconds=60, at=at + timedelta(seconds=61))
        self.assertEqual(state["lease"]["owner"], "builder-2")

    def test_wrong_role_cannot_claim(self):
        with self.assertRaises(RelayStateError):
            claim(base_state("READY_FOR_BUILDER"), "LCR-C", "verifier")

    def test_clear_lease_requires_owner_when_supplied(self):
        state = claim(base_state("READY_FOR_BUILDER"), "LCR-B", "builder-1")
        with self.assertRaises(RelayStateError):
            clear_lease(state, owner="builder-2")
        state = clear_lease(state, owner="builder-1")
        self.assertIsNone(state["lease"])


class PacketTests(unittest.TestCase):
    def make_packet(self) -> tuple[dict, dict]:
        state = base_state("READY_FOR_BUILDER")
        state = claim(state, "LCR-B", "builder-1")
        value = packet(
            state=state,
            run_id="RUN-001",
            source_role="LCR-A",
            target_role="LCR-B",
            status="READY_FOR_BUILDER",
            task="create deterministic proof artifact",
            acceptance=["artifact equals LIDIYA_CLOUD_RELAY_OK"],
        )
        return state, value

    def test_packet_consumes_once(self):
        state, value = self.make_packet()
        consumed = consume_once(state, value)
        self.assertEqual(consumed["last_packet_sha256"], value["packet_sha256"])
        with self.assertRaises(RelayStateError):
            consume_once(consumed, value)

    def test_tampered_packet_is_rejected(self):
        state, value = self.make_packet()
        value["task"] = "tampered"
        with self.assertRaises(RelayStateError):
            consume_once(state, value)

    def test_retry_increments_attempt(self):
        state = retry_step(base_state("READY_FOR_BUILDER"))
        self.assertEqual(state["attempt"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
