from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from cloud_relay_state import RelayStateError, claim, clear_lease, consume_once, packet, retry_step, set_pending_packet, transition

UTC = timezone.utc


def base_state(status: str = "IDLE") -> dict:
    return {"schema_version": "2.0", "mission_id": "LCR-ROUNDTRIP-0001", "status": status, "step_id": 1, "attempt": 0, "current_role": "LCR-A", "next_role": "LCR-A", "candidate_ref": "lidiya-cloud-relay-v2", "last_packet_sha256": None, "pending_packet": None, "lease": None}


class TransitionTests(unittest.TestCase):
    def test_happy_path_roles(self):
        state = transition(base_state(), "COORDINATING")
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
        state = claim(base_state("READY_FOR_BUILDER"), "LCR-B", "builder-1", ttl_seconds=60, at=at)
        with self.assertRaises(RelayStateError):
            claim(state, "LCR-B", "builder-2", ttl_seconds=60, at=at + timedelta(seconds=10))

    def test_expired_lease_can_be_reclaimed(self):
        at = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
        state = claim(base_state("READY_FOR_BUILDER"), "LCR-B", "builder-1", ttl_seconds=60, at=at)
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
        state = claim(base_state("READY_FOR_BUILDER"), "LCR-B", "builder-1")
        value = packet(state=state, run_id="RUN-001", source_role="LCR-A", target_role="LCR-B", status="READY_FOR_BUILDER", task="create deterministic proof artifact", acceptance=["artifact equals LIDIYA_CLOUD_RELAY_OK"])
        return state, value

    def test_packet_consumes_once(self):
        state, value = self.make_packet()
        consumed = consume_once(state, value)
        self.assertEqual(consumed["last_packet_sha256"], value["packet_sha256"])
        self.assertIn(value["packet_sha256"], consumed["consumed_packet_sha256"])
        with self.assertRaises(RelayStateError):
            consume_once(consumed, value)

    def test_non_adjacent_replay_is_rejected(self):
        state = base_state("READY_FOR_BUILDER")
        p1 = packet(state=state, run_id="RUN-P1", source_role="LCR-A", target_role="LCR-B", status="READY_FOR_BUILDER", task="first", acceptance=["consume once"])
        state = consume_once(state, p1)
        p2 = packet(state=state, run_id="RUN-P2", source_role="LCR-B", target_role="LCR-C", status="READY_FOR_VERIFY", task="second", acceptance=["consume once"])
        state = consume_once(state, p2)
        self.assertEqual(state["last_packet_sha256"], p2["packet_sha256"])
        with self.assertRaises(RelayStateError):
            consume_once(state, p1)

    def test_legacy_last_packet_is_seeded_into_replay_history(self):
        state = base_state("READY_FOR_BUILDER")
        p1 = packet(state=state, run_id="RUN-LEGACY", source_role="LCR-A", target_role="LCR-B", status="READY_FOR_BUILDER", task="legacy", acceptance=["reject replay"])
        state["last_packet_sha256"] = p1["packet_sha256"]
        with self.assertRaises(RelayStateError):
            consume_once(state, p1)

    def test_pending_outbound_does_not_preconsume_packet(self):
        state = base_state("READY_FOR_BUILDER")
        inbound = packet(state=state, run_id="RUN-REPAIR", source_role="LCR-C", target_role="LCR-B", status="READY_FOR_BUILDER", task="repair consume semantics", acceptance=["recipient can consume outbound once"])
        state = consume_once(state, inbound)
        last_consumed = state["last_packet_sha256"]
        outbound = packet(state=state, run_id="RUN-REPAIR", source_role="LCR-B", target_role="LCR-C", status="READY_FOR_VERIFY", task="verify repaired consume semantics", acceptance=["consume succeeds once and replay fails"])
        emitted = set_pending_packet(state, "packets/B-TO-C.json")
        self.assertEqual(emitted["last_packet_sha256"], last_consumed)
        self.assertEqual(emitted["pending_packet"], "packets/B-TO-C.json")
        self.assertNotEqual(emitted["last_packet_sha256"], outbound["packet_sha256"])
        consumed = consume_once(emitted, outbound)
        self.assertEqual(consumed["last_packet_sha256"], outbound["packet_sha256"])
        with self.assertRaises(RelayStateError):
            consume_once(consumed, outbound)

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
