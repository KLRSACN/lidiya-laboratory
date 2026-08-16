import json
import tempfile
import unittest
from pathlib import Path

from heartbeat_engine import (
    COMPACT_CADENCE_PULSES,
    PULSE_FILTER_HEX_LEN,
    HeartbeatEngine,
    HeartbeatError,
    InvalidHeartbeatConfig,
    StaleWriterError,
    canonical_pulse_id,
    validate_experience_event,
)


class HeartbeatEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "heartbeat.json"

    def tearDown(self):
        self.tmp.cleanup()

    def engine(self, interval=300):
        return HeartbeatEngine(self.state_path, interval_seconds=interval)

    def test_interval_lower_bound(self):
        self.assertEqual(self.engine(300).state.interval_seconds, 300)

    def test_interval_upper_bound(self):
        self.assertEqual(self.engine(600).state.interval_seconds, 600)

    def test_interval_below_rejected(self):
        with self.assertRaises(InvalidHeartbeatConfig):
            self.engine(299)

    def test_interval_above_rejected(self):
        with self.assertRaises(InvalidHeartbeatConfig):
            self.engine(601)

    def test_duplicate_pulse_is_noop(self):
        e = self.engine()
        self.assertTrue(e.tick(now=0, pulse_id="p1").executed)
        before = e.snapshot()
        r = e.tick(now=300, pulse_id="p1")
        self.assertEqual(r.disposition, "DUPLICATE_NO_OP")
        self.assertEqual(before, e.snapshot())

    def test_not_due_is_noop(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1")
        before = e.snapshot()
        self.assertFalse(e.tick(now=299, pulse_id="p2").executed)
        self.assertEqual(before, e.snapshot())

    def test_restart_preserves_sequence_and_cursor(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1")
        e.tick(now=300, pulse_id="p2")
        r = self.engine()
        self.assertEqual(
            (r.state.pulse_sequence, r.state.event_cursor, r.state.next_due_at),
            (2, 2, 600),
        )

    def test_bounded_catchup_never_bursts(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1")
        self.assertTrue(e.tick(now=7200, pulse_id="p2").executed)
        self.assertEqual(e.state.next_due_at, 7500)
        self.assertFalse(e.tick(now=7200, pulse_id="p3").executed)

    def test_two_misses_marks_stale(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1", endpoint_ok=False)
        e.tick(now=300, pulse_id="p2", endpoint_ok=False)
        self.assertEqual(e.state.endpoint_status, "STALE")

    def test_verified_recovery_is_deduped(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1", endpoint_ok=False)
        e.tick(now=300, pulse_id="p2", endpoint_ok=False)
        self.assertTrue(e.mark_verified_recovery(recovery_id="r1")["changed"])
        before = e.snapshot()
        self.assertFalse(e.mark_verified_recovery(recovery_id="r1")["changed"])
        self.assertEqual(before, e.snapshot())

    def test_compact_every_12_pulses(self):
        e = self.engine()
        flags = [
            e.tick(now=i * 300, pulse_id=f"p{i}").compact_required
            for i in range(COMPACT_CADENCE_PULSES)
        ]
        self.assertEqual(flags[:-1], [False] * 11)
        self.assertTrue(flags[-1])
        self.assertEqual(e.state.compact_records, 1)

    def test_material_stale_anomaly_compacts_immediately(self):
        e = self.engine()
        self.assertFalse(e.tick(now=0, pulse_id="p1", endpoint_ok=False).compact_required)
        self.assertTrue(e.tick(now=300, pulse_id="p2", endpoint_ok=False).compact_required)

    def test_stale_writer_rejected(self):
        e = self.engine()
        g = e.state.writer_generation
        e.tick(now=0, pulse_id="p1", expected_generation=g)
        with self.assertRaises(StaleWriterError):
            e.tick(now=300, pulse_id="p2", expected_generation=g)

    def test_24h_virtual_is_exactly_288_unique_pulses(self):
        e = self.engine()
        ids = set()
        for i in range(288):
            r = e.tick(now=i * 300)
            self.assertTrue(r.executed)
            ids.add(r.pulse_id)
        self.assertEqual(
            (e.state.pulse_sequence, e.state.event_cursor, len(ids)),
            (288, 288, 288),
        )

    def test_288_pulses_have_zero_experience_delta(self):
        e = self.engine()
        for i in range(288):
            self.assertEqual(
                e.tick(now=i * 300).experience_delta,
                {
                    "recurrence": 0,
                    "emotion": 0,
                    "self_identity_relevance": 0,
                    "verified_count": 0,
                    "p_base_evidence": 0,
                },
            )

    def test_state_has_no_formal_authority_fields(self):
        forbidden = {"mission_state", "pending_packet", "dialogue_sequence", "current_role"}
        self.assertTrue(forbidden.isdisjoint(set(self.engine().snapshot())))

    def test_experience_requires_distinct_source_event_and_provenance(self):
        validate_experience_event(
            {"source_event_id": "evt-1", "provenance": "sensor:test"},
            pulse_id="p1",
        )
        with self.assertRaises(HeartbeatError):
            validate_experience_event(
                {"source_event_id": "p1", "provenance": "sensor:test"},
                pulse_id="p1",
            )
        with self.assertRaises(HeartbeatError):
            validate_experience_event(
                {"source_event_id": "evt-1", "provenance": ""}
            )

    def test_event_cursor_rollback_fails_on_restart(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1")
        data = json.loads(self.state_path.read_text())
        data["event_cursor"] = 0
        self.state_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(HeartbeatError):
            self.engine()

    def test_replay_prefix_after_more_than_512_is_duplicate_noop(self):
        e = self.engine()
        for i in range(600):
            self.assertTrue(e.tick(now=i * 300, pulse_id=f"p{i}").executed)
        before = e.snapshot()
        r = e.tick(now=600 * 300, pulse_id="p0")
        self.assertEqual(r.disposition, "DUPLICATE_NO_OP")
        self.assertFalse(r.executed)
        self.assertEqual(before, e.snapshot())

    def test_restart_replay_prefix_after_more_than_512_is_duplicate_noop(self):
        e = self.engine()
        for i in range(600):
            self.assertTrue(e.tick(now=i * 300, pulse_id=f"p{i}").executed)
        e = self.engine()
        before = e.snapshot()
        r = e.tick(now=600 * 300, pulse_id="p1")
        self.assertEqual(r.disposition, "DUPLICATE_NO_OP")
        self.assertEqual(before, e.snapshot())

    def test_dedupe_storage_is_bounded(self):
        e = self.engine()
        for i in range(700):
            e.tick(now=i * 300, pulse_id=f"p{i}")
        self.assertEqual(len(e.state.pulse_filter_hex), PULSE_FILTER_HEX_LEN)
        self.assertNotIn("recent_pulse_ids", e.snapshot())

    def test_known_bloom_false_positive_cannot_deadlock_canonical_path(self):
        e = self.engine()
        result = None
        for i in range(689):
            result = e.tick(now=i * 300)
            self.assertTrue(result.executed, (i + 1, result))
        self.assertEqual(result.pulse_sequence, 689)
        self.assertEqual(result.pulse_id, canonical_pulse_id(689, 688 * 300))
        self.assertEqual(result.pulse_id, "hb-6bfbc4b7f509f94691f9dec3")
        self.assertEqual(e.state.next_due_at, 689 * 300)

    def test_10000_canonical_pulses_zero_false_duplicate_with_restart(self):
        e = self.engine()
        ids = set()
        zero = {
            "recurrence": 0,
            "emotion": 0,
            "self_identity_relevance": 0,
            "verified_count": 0,
            "p_base_evidence": 0,
        }
        for i in range(10000):
            if i == 5000:
                e = self.engine()
                self.assertEqual(e.state.pulse_sequence, 5000)
                self.assertEqual(e.state.next_due_at, 5000 * 300)
            r = e.tick(now=i * 300)
            self.assertEqual(r.disposition, "EXECUTED", (i + 1, r))
            self.assertTrue(r.executed)
            self.assertNotIn(r.pulse_id, ids)
            ids.add(r.pulse_id)
            self.assertEqual(r.experience_delta, zero)
        self.assertEqual(e.state.pulse_sequence, 10000)
        self.assertEqual(e.state.event_cursor, 10000)
        self.assertEqual(len(ids), 10000)
        self.assertEqual(len(e.state.pulse_filter_hex), PULSE_FILTER_HEX_LEN)

        e = self.engine()
        before = e.snapshot()
        replay = e.tick(now=10000 * 300, pulse_id=canonical_pulse_id(1, 0))
        self.assertEqual(replay.disposition, "DUPLICATE_NO_OP")
        self.assertFalse(replay.executed)
        self.assertEqual(before, e.snapshot())


if __name__ == "__main__":
    unittest.main()
