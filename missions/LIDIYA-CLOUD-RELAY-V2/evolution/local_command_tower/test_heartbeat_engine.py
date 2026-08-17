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
    parse_canonical_pulse_id,
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

    def test_interval_bounds(self):
        self.assertEqual(self.engine(300).state.interval_seconds, 300)
        self.state_path.unlink()
        self.assertEqual(self.engine(600).state.interval_seconds, 600)

    def test_interval_outside_rejected(self):
        with self.assertRaises(InvalidHeartbeatConfig): self.engine(299)
        with self.assertRaises(InvalidHeartbeatConfig): self.engine(601)

    def test_structured_id_roundtrip(self):
        pid = canonical_pulse_id(7, 1800)
        self.assertEqual(parse_canonical_pulse_id(pid), (7, 1800))
        self.assertTrue(pid.startswith("hb2-7-1800-"))

    def test_opaque_never_seen_id_invalid_and_state_unchanged(self):
        e = self.engine()
        before = e.snapshot()
        r = e.tick(now=0, pulse_id="opaque-never-seen")
        self.assertEqual(r.disposition, "INVALID_EXTERNAL_PULSE_ID_NO_OP")
        self.assertFalse(r.executed)
        self.assertEqual(before, e.snapshot())

    def test_constructed_prior_bloom_collision_opaque_is_invalid_not_duplicate(self):
        e = self.engine()
        before = e.snapshot()
        r = e.tick(now=0, pulse_id="hb-6bfbc4b7f509f94691f9dec3")
        self.assertEqual(r.disposition, "INVALID_EXTERNAL_PULSE_ID_NO_OP")
        self.assertEqual(before, e.snapshot())

    def test_explicit_valid_next_structured_executes(self):
        e = self.engine()
        pid = canonical_pulse_id(1, 0)
        r = e.tick(now=0, pulse_id=pid)
        self.assertEqual(r.disposition, "EXECUTED")
        self.assertTrue(r.executed)

    def test_structured_old_seq1_after_more_than_512_and_restart_duplicate(self):
        e = self.engine()
        first = None
        for i in range(600):
            r = e.tick(now=i*300)
            if i == 0: first = r.pulse_id
        e = self.engine()
        before = e.snapshot()
        r = e.tick(now=600*300, pulse_id=first)
        self.assertEqual(r.disposition, "DUPLICATE_NO_OP")
        self.assertEqual(before, e.snapshot())

    def test_structured_old_seq512_after_10000_and_restart_duplicate(self):
        e = self.engine()
        p512 = None
        for i in range(10000):
            r = e.tick(now=i*300)
            if i == 511: p512 = r.pulse_id
        e = self.engine()
        before = e.snapshot()
        r = e.tick(now=10000*300, pulse_id=p512)
        self.assertEqual(r.disposition, "DUPLICATE_NO_OP")
        self.assertEqual(before, e.snapshot())

    def test_structured_future_seq_plus2_out_of_order(self):
        e = self.engine()
        before = e.snapshot()
        pid = canonical_pulse_id(2, 300)
        r = e.tick(now=0, pulse_id=pid)
        self.assertEqual(r.disposition, "OUT_OF_ORDER_NO_OP")
        self.assertEqual(before, e.snapshot())

    def test_structured_tampered_digest_invalid(self):
        e = self.engine()
        good = canonical_pulse_id(1,0)
        bad = good[:-1] + ("0" if good[-1] != "0" else "1")
        before = e.snapshot()
        r = e.tick(now=0, pulse_id=bad)
        self.assertEqual(r.disposition, "INVALID_EXTERNAL_PULSE_ID_NO_OP")
        self.assertEqual(before, e.snapshot())

    def test_structured_wrong_time_invalid(self):
        e = self.engine()
        before = e.snapshot()
        pid = canonical_pulse_id(1, 300)
        r = e.tick(now=0, pulse_id=pid)
        self.assertEqual(r.disposition, "INVALID_CANONICAL_ID_NO_OP")
        self.assertEqual(before, e.snapshot())

    def test_not_due_is_noop(self):
        e = self.engine()
        e.tick(now=0)
        before = e.snapshot()
        r = e.tick(now=299)
        self.assertEqual(r.disposition, "NOT_DUE")
        self.assertEqual(before, e.snapshot())

    def test_restart_preserves_sequence_and_cursor(self):
        e = self.engine()
        e.tick(now=0); e.tick(now=300)
        r = self.engine()
        self.assertEqual((r.state.pulse_sequence,r.state.event_cursor,r.state.next_due_at),(2,2,600))

    def test_bounded_catchup_never_bursts(self):
        e = self.engine()
        e.tick(now=0)
        self.assertTrue(e.tick(now=7200).executed)
        self.assertEqual(e.state.next_due_at, 7500)
        self.assertFalse(e.tick(now=7200).executed)

    def test_two_misses_marks_stale(self):
        e = self.engine()
        e.tick(now=0, endpoint_ok=False)
        e.tick(now=300, endpoint_ok=False)
        self.assertEqual(e.state.endpoint_status, "STALE")

    def test_verified_recovery_is_deduped(self):
        e = self.engine()
        e.tick(now=0, endpoint_ok=False); e.tick(now=300, endpoint_ok=False)
        self.assertTrue(e.mark_verified_recovery(recovery_id="r1")["changed"])
        before=e.snapshot()
        self.assertFalse(e.mark_verified_recovery(recovery_id="r1")["changed"])
        self.assertEqual(before,e.snapshot())

    def test_compact_every_12_pulses(self):
        e=self.engine()
        flags=[e.tick(now=i*300).compact_required for i in range(COMPACT_CADENCE_PULSES)]
        self.assertEqual(flags[:-1],[False]*11); self.assertTrue(flags[-1])

    def test_material_stale_anomaly_compacts_immediately(self):
        e=self.engine()
        self.assertFalse(e.tick(now=0,endpoint_ok=False).compact_required)
        self.assertTrue(e.tick(now=300,endpoint_ok=False).compact_required)

    def test_stale_writer_rejected(self):
        e=self.engine(); g=e.state.writer_generation
        e.tick(now=0, expected_generation=g)
        with self.assertRaises(StaleWriterError):
            e.tick(now=300, expected_generation=g)

    def test_24h_virtual_exact_288_zero_experience(self):
        e=self.engine(); ids=set()
        for i in range(288):
            r=e.tick(now=i*300); ids.add(r.pulse_id)
            self.assertEqual(sum(r.experience_delta.values()),0)
        self.assertEqual((e.state.pulse_sequence,e.state.event_cursor,len(ids)),(288,288,288))

    def test_state_has_no_formal_authority_fields(self):
        forbidden={"mission_state","pending_packet","dialogue_sequence","current_role"}
        self.assertTrue(forbidden.isdisjoint(set(self.engine().snapshot())))

    def test_experience_requires_distinct_source_event_and_provenance(self):
        validate_experience_event({"source_event_id":"evt-1","provenance":"sensor:test"}, pulse_id="p1")
        with self.assertRaises(HeartbeatError):
            validate_experience_event({"source_event_id":"p1","provenance":"sensor:test"}, pulse_id="p1")
        with self.assertRaises(HeartbeatError):
            validate_experience_event({"source_event_id":"evt-1","provenance":""})

    def test_event_cursor_rollback_fails_on_restart(self):
        e=self.engine(); e.tick(now=0)
        data=json.loads(self.state_path.read_text()); data["event_cursor"]=0
        self.state_path.write_text(json.dumps(data),encoding="utf-8")
        with self.assertRaises(HeartbeatError): self.engine()

    def test_legacy_filter_storage_bounded_and_non_authoritative(self):
        e=self.engine()
        initial=e.state.pulse_filter_hex
        for i in range(700): e.tick(now=i*300)
        self.assertEqual(len(e.state.pulse_filter_hex),PULSE_FILTER_HEX_LEN)
        self.assertEqual(e.state.pulse_filter_hex,initial)

    def test_historical_pulse689_executes(self):
        e=self.engine(); result=None
        for i in range(689):
            result=e.tick(now=i*300)
            self.assertTrue(result.executed,(i+1,result))
        self.assertEqual(result.pulse_sequence,689)

    def test_10000_canonical_pulses_midpoint_restart_zero_false_duplicate_or_stall(self):
        e=self.engine(); ids=set()
        for i in range(10000):
            if i==5000:
                e=self.engine()
                self.assertEqual(e.state.pulse_sequence,5000)
            r=e.tick(now=i*300)
            self.assertEqual(r.disposition,"EXECUTED",(i+1,r))
            self.assertTrue(r.executed)
            self.assertNotIn(r.pulse_id,ids)
            ids.add(r.pulse_id)
            self.assertEqual(sum(r.experience_delta.values()),0)
        self.assertEqual((e.state.pulse_sequence,e.state.event_cursor,len(ids)),(10000,10000,10000))
        r=e.tick(now=10000*300)
        self.assertEqual(r.disposition,"EXECUTED")
        self.assertEqual(r.pulse_sequence,10001)

if __name__=="__main__":
    unittest.main()
