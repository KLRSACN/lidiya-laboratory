from __future__ import annotations

import argparse
import json
import sqlite3
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from relay_protocol import RelayEnvelope, parse_relay_output

UTC = timezone.utc


class RelayStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS windows (
                window_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                debug_port INTEGER NOT NULL,
                marker TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'READY',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                action TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivered_at TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS schedules (
                schedule_id TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                wake_at TEXT NOT NULL,
                event TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING'
            );
            CREATE INDEX IF NOT EXISTS idx_messages_target_status
                ON messages(target, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_schedules_due
                ON schedules(status, wake_at);
            """
        )
        self.connection.commit()

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    def register_window(self, window_id: str, role: str, debug_port: int, marker: str) -> None:
        self.connection.execute(
            """
            INSERT INTO windows(window_id, role, debug_port, marker, status, updated_at)
            VALUES (?, ?, ?, ?, 'READY', ?)
            ON CONFLICT(window_id) DO UPDATE SET
              role=excluded.role,
              debug_port=excluded.debug_port,
              marker=excluded.marker,
              updated_at=excluded.updated_at
            """,
            (window_id, role, debug_port, marker, self.now()),
        )
        self.connection.commit()

    def enqueue(self, mission_id: str, source: str, envelope: RelayEnvelope) -> str:
        message_id = f"MSG-{uuid.uuid4().hex[:12].upper()}"
        self.connection.execute(
            """
            INSERT INTO messages(
              message_id, mission_id, source, target, action, payload, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                message_id,
                mission_id,
                source,
                envelope.target,
                envelope.action,
                envelope.payload,
                self.now(),
            ),
        )
        if envelope.wake_after_seconds is not None:
            wake_at = datetime.now(UTC) + timedelta(seconds=envelope.wake_after_seconds)
            self.connection.execute(
                """
                INSERT INTO schedules(schedule_id, target, wake_at, event, payload)
                VALUES (?, ?, ?, 'MESSAGE_WAKE', ?)
                """,
                (
                    f"SCH-{uuid.uuid4().hex[:12].upper()}",
                    envelope.target,
                    wake_at.isoformat(),
                    json.dumps({"message_id": message_id}, ensure_ascii=False),
                ),
            )
        self.connection.commit()
        return message_id

    def next_message(self, target: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT * FROM messages
            WHERE target=? AND status='PENDING'
            ORDER BY created_at ASC LIMIT 1
            """,
            (target,),
        ).fetchone()

    def mark_delivered(self, message_id: str) -> None:
        """Record that the message was sent and is awaiting a response."""
        self.connection.execute(
            """
            UPDATE messages
            SET status='AWAITING_RESPONSE', delivered_at=?
            WHERE message_id=?
            """,
            (self.now(), message_id),
        )
        self.connection.commit()

    def mark_completed(self, message_id: str) -> None:
        """Record that a complete response was successfully received."""
        self.connection.execute(
            """
            UPDATE messages
            SET status='COMPLETED', completed_at=?
            WHERE message_id=?
            """,
            (self.now(), message_id),
        )
        self.connection.commit()

    def mark_timed_out(self, message_id: str) -> None:
        """Record a response timeout without making the message resendable."""
        self.connection.execute(
            "UPDATE messages SET status='TIMED_OUT' WHERE message_id=?",
            (message_id,),
        )
        self.connection.commit()

    def mark_failed(self, message_id: str) -> None:
        """Record a navigation or send failure without automatic resending."""
        self.connection.execute(
            "UPDATE messages SET status='FAILED' WHERE message_id=?",
            (message_id,),
        )
        self.connection.commit()

    def due_wakes(self) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """
                SELECT * FROM schedules
                WHERE status='PENDING' AND wake_at<=?
                ORDER BY wake_at ASC
                """,
                (self.now(),),
            )
        )

    def complete_wake(self, schedule_id: str) -> None:
        self.connection.execute(
            "UPDATE schedules SET status='COMPLETED' WHERE schedule_id=?",
            (schedule_id,),
        )
        self.connection.commit()


def ingest_file(store: RelayStore, mission_id: str, source: str, file_path: str) -> str:
    text = Path(file_path).read_text(encoding="utf-8")
    envelope = parse_relay_output(text)
    return store.enqueue(mission_id, source, envelope)


def scheduler_loop(store: RelayStore, interval_seconds: int) -> None:
    while True:
        for wake in store.due_wakes():
            print(json.dumps({"event": wake["event"], "target": wake["target"], "payload": json.loads(wake["payload"])}))
            store.complete_wake(wake["schedule_id"])
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="NAV Relay MVP")
    parser.add_argument("--db", default="nav_relay_mvp.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register")
    register.add_argument("window_id")
    register.add_argument("role")
    register.add_argument("debug_port", type=int)
    register.add_argument("marker")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("mission_id")
    ingest.add_argument("source")
    ingest.add_argument("file_path")

    pull = sub.add_parser("pull")
    pull.add_argument("target")

    scheduler = sub.add_parser("scheduler")
    scheduler.add_argument("--interval", type=int, default=5)

    args = parser.parse_args()
    store = RelayStore(args.db)

    if args.command == "register":
        store.register_window(args.window_id, args.role, args.debug_port, args.marker)
        print("REGISTERED")
    elif args.command == "ingest":
        print(ingest_file(store, args.mission_id, args.source, args.file_path))
    elif args.command == "pull":
        row = store.next_message(args.target)
        if row is None:
            print("NO_MESSAGE")
        else:
            print(json.dumps(dict(row), ensure_ascii=False, indent=2))
    elif args.command == "scheduler":
        scheduler_loop(store, args.interval)


if __name__ == "__main__":
    main()
