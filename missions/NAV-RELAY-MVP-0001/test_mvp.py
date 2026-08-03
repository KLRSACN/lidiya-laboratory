import tempfile
import unittest
from pathlib import Path

from coordinator_mvp import decide
from relay_mvp import RelayStore
from relay_protocol import ProtocolError, parse_relay_output


VALID = """[RELAY_READY]
[TARGET:WINDOW-02]
[ACTION:SEND]
[WAKE_AFTER:5]

[RELAY_OUTPUT_BEGIN]
STATE=BUILDER_TASK_COMPLETED
[RELAY_OUTPUT_END]
"""


class ProtocolTests(unittest.TestCase):
    def test_parse_valid(self):
        env = parse_relay_output(VALID)
        self.assertEqual(env.target, "WINDOW-02")
        self.assertEqual(env.action, "SEND")
        self.assertEqual(env.wake_after_seconds, 5)

    def test_reject_missing_marker(self):
        with self.assertRaises(ProtocolError):
            parse_relay_output(VALID.replace("[RELAY_READY]", ""))

    def test_reject_empty_payload(self):
        with self.assertRaises(ProtocolError):
            parse_relay_output(VALID.replace("STATE=BUILDER_TASK_COMPLETED", ""))


class RelayTests(unittest.TestCase):
    def test_register_enqueue_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "relay.sqlite3")
            store.register_window("WINDOW-02", "REVIEWER", 9224, "[LIDIYA:WINDOW-02]")
            message_id = store.enqueue("NAV-RELAY-MVP-0001", "WINDOW-01", parse_relay_output(VALID))
            row = store.next_message("WINDOW-02")
            self.assertIsNotNone(row)
            self.assertEqual(row["message_id"], message_id)
            self.assertEqual(row["status"], "PENDING")
            store.connection.close()

    def test_wake_is_scheduled(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "relay.sqlite3")
            store.enqueue("NAV-RELAY-MVP-0001", "WINDOW-01", parse_relay_output(VALID))
            count = store.connection.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
            self.assertEqual(count, 1)
            store.connection.close()


class CoordinatorTests(unittest.TestCase):
    def test_builder_completion_routes_to_reviewer(self):
        decision = decide("BUILDER_V0_3_INTEGRITY_REPAIRED")
        self.assertEqual(decision.target, "WINDOW-02")

    def test_blocked_routes_to_builder(self):
        decision = decide("BUILDER_TASK_BLOCKED")
        self.assertEqual(decision.target, "WINDOW-01")


if __name__ == "__main__":
    unittest.main(verbosity=2)

