from __future__ import annotations

import argparse

from relay_mvp import RelayStore
from relay_protocol import RelayEnvelope


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject the first NAV Relay roundtrip")
    parser.add_argument("--db", default="nav_relay_mvp.sqlite3")
    parser.add_argument("--target", default="WINDOW-01")
    args = parser.parse_args()

    store = RelayStore(args.db)
    payload = """You are the Builder worker in NAV-RELAY-MVP-0001.
Reply only with the following routable packet, replacing nothing:

[RELAY_READY]
[TARGET:WINDOW-00]
[ACTION:SEND]
[WAKE_AFTER:5]
[RELAY_OUTPUT_BEGIN]
STATE=NAVIGATOR_ROUNDTRIP_BUILDER_ACK
SOURCE=WINDOW-01
TARGET=WINDOW-00
READY_FOR_NEXT_TASK=true
[RELAY_OUTPUT_END]
"""
    envelope = RelayEnvelope(
        target=args.target,
        action="SEND",
        payload=payload,
        wake_after_seconds=5,
    )
    message_id = store.enqueue(
        mission_id="NAV-RELAY-MVP-0001",
        source="WINDOW-00",
        envelope=envelope,
    )
    print(message_id)


if __name__ == "__main__":
    main()
