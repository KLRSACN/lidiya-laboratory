from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from navigator_adapter import NavigatorAdapter, NavigatorError
from relay_mvp import RelayStore
from relay_protocol import RelayEnvelope


class NavigatorAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "relay.sqlite3"
        self.store = RelayStore(self.db)
        self.store.register_window("WINDOW-01", "BUILDER", 9223, "[LIDIYA:WINDOW-01]")
        self.adapter = NavigatorAdapter(self.store, stable_seconds=0.0, poll_seconds=0.0, response_timeout_seconds=0.1)

    def tearDown(self) -> None:
        self.store.connection.close()
        self.tempdir.cleanup()

    def test_get_registered_window(self) -> None:
        record = self.adapter.get_window("WINDOW-01")
        self.assertEqual(record.debug_port, 9223)
        self.assertEqual(record.marker, "[LIDIYA:WINDOW-01]")

    def test_missing_window_is_rejected(self) -> None:
        with self.assertRaises(NavigatorError):
            self.adapter.get_window("WINDOW-X")

    def test_ingest_response_routes_to_target(self) -> None:
        response = """[RELAY_READY]
[TARGET:WINDOW-01]
[ACTION:SEND]
[RELAY_OUTPUT_BEGIN]
Please continue.
[RELAY_OUTPUT_END]
"""
        message_id = self.adapter.ingest_response("NAV-RELAY-MVP-0001", "WINDOW-00", response)
        row = self.store.next_message("WINDOW-01")
        self.assertIsNotNone(row)
        self.assertEqual(row["message_id"], message_id)
        self.assertEqual(row["payload"], "Please continue.")

    def test_deliver_one_returns_none_without_message(self) -> None:
        self.assertIsNone(self.adapter.deliver_one("WINDOW-01"))

    def test_enqueue_message_remains_pending_before_navigation(self) -> None:
        envelope = RelayEnvelope(target="WINDOW-01", action="SEND", payload="Task", wake_after_seconds=None)
        message_id = self.store.enqueue("NAV-RELAY-MVP-0001", "WINDOW-00", envelope)
        row = self.store.next_message("WINDOW-01")
        self.assertEqual(row["message_id"], message_id)
        self.assertEqual(row["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
