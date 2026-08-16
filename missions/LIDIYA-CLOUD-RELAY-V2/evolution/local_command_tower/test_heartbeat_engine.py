import json
import tempfile
import unittest
from pathlib import Path

from heartbeat_engine import (
    COMPACT_CADENCE_PULSES,
    HeartbeatEngine,
    HeartbeatError,
    InvalidHeartbeatConfig,
    StaleWriterError,
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
        first = e.tick(now=0, pulse_id="p1")
        before = e.snapshot()
        dup = e.tick(now=300, pulse_id="p1")
        after = e.snapshot()
        self.assertTrue(first.executed)
        self.assertFalse(dup.executed)
        self.assertEqual(dup.disposition, "DUPLICATE_NO_OP")
        self.assertEqual(before, after)

    def test_not_due_is_noop(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1")
        before = e.snapshot()
        r = e.tick(now=299, pulse_id="p2")
        self.assertFalse(r.executed)
        self.assertEqual(before, e.snapshot())

    def test_restart_preserves_sequence_and_cursor(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1")
        e.tick(now=300, pulse_id="p2")
        restarted = self.engine()
        self.assertEqual(restarted.state.pulse_sequence, 2)
        self.assertEqual(restarted.state.event_cursor, 2)
        self.assertEqual(restarted.state.next_due_at, 600)

    def test_bounded_catchup_never_bursts(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1")
        r = e.tick(now=7200, pulse_id="p2")
        self.assertTrue(r.executed)
        self.assertEqual(e.state.pulse_sequence, 2)
        self.assertEqual(e.state.next_due_at, 7500)
        self.assertFalse(e.tick(now=7200, pulse_id="p3").executed)

    def test_two_misses_marks_stale(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1", endpoint_ok=False)
        self.assertNotEqual(e.state.endpoint_status, "STALE")
        e.tick(now=300, pulse_id="p2", endpoint_ok=False)
        self.assertEqual(e.state.endpoint_status, "STALE")

    def test_verified_recovery_is_deduped(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1", endpoint_ok=False)
        e.tick(now=300, pulse_id="p2", endpoint_ok=False)
        first = e.mark_verified_recovery(recovery_id="r1")
        before = e.snapshot()
        second = e.mark_verified_recovery(recovery_id="r1")
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(before, e.snapshot())

    def test_compact_every_12_pulses(self):
        e = self.engine()
        flags = []
        for i in range(COMPACT_CADENCE_PULSES):
            flags.append(e.tick(now=i * 300, pulse_id=f"p{i}").compact_required)
        self.assertEqual(flags[:-1], [False] * 11)
        self.assertTrue(flags[-1])
        self.assertEqual(e.state.compact_records, 1)

    def test_material_stale_anomaly_compacts_immediately(self):
        e = self.engine()
        self.assertFalse(e.tick(now=0, pulse_id="p1", endpoint_ok=False).compact_required)
        self.assertTrue(e.tick(now=300, pulse_id="p2", endpoint_ok=False).compact_required)

    def test_stale_writer_rejected(self):
        e = self.engine()
        generation = e.state.writer_generation
        e.tick(now=0, pulse_id="p1", expected_generation=generation)
        with self.assertRaises(StaleWriterError):
            e.tick(now=300, pulse_id="p2", expected_generation=generation)

    def test_24h_virtual_is_exactly_288_unique_pulses(self):
        e = self.engine()
        ids = set()
        for i in range(288):
            r = e.tick(now=i * 300)
            self.assertTrue(r.executed)
            ids.add(r.pulse_id)
        self.assertEqual(e.state.pulse_sequence, 288)
        self.assertEqual(e.state.event_cursor, 288)
        self.assertEqual(len(ids), 288)

    def test_288_pulses_have_zero_experience_delta(self):
        e = self.engine()
        for i in range(288):
            r = e.tick(now=i * 300)
            self.assertEqual(r.experience_delta, {
                "recurrence": 0,
                "emotion": 0,
                "self_identity_relevance": 0,
                "verified_count": 0,
                "p_base_evidence": 0,
            })

    def test_state_has_no_formal_authority_fields(self):
        e = self.engine()
        keys = set(e.snapshot())
        forbidden = {"mission_state", "pending_packet", "dialogue_sequence", "current_role"}
        self.assertTrue(forbidden.isdisjoint(keys))

    def test_experience_requires_distinct_source_event_and_provenance(self):
        validate_experience_event({"source_event_id":"evt-1","provenance":"sensor:test"}, pulse_id="p1")
        with self.assertRaises(HeartbeatError):
            validate_experience_event({"source_event_id":"p1","provenance":"sensor:test"}, pulse_id="p1")
        with self.assertRaises(HeartbeatError):
            validate_experience_event({"source_event_id":"evt-1","provenance":""})

    def test_event_cursor_rollback_fails_on_restart(self):
        e = self.engine()
        e.tick(now=0, pulse_id="p1")
        data = json.loads(self.state_path.read_text())
        data["event_cursor"] = 0
        data["pulse_sequence"] = 1
        self.state_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(HeartbeatError):
            self.engine()


if __name__ == "__main__":
    unittest.main()
