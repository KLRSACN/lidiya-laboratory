from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


TASK_STATES = {
    "RECEIVED",
    "PLANNED",
    "RUNNING",
    "VERIFYING",
    "RETRYING",
    "ESCALATED",
    "WAITING_APPROVAL",
    "SUCCESS",
    "FAILED",
    "CANCELLED",
}

TERMINAL_STATES = {"SUCCESS", "FAILED", "CANCELLED"}


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    title: str
    goal: str
    status: str
    priority: int
    attempts: int
    max_attempts: int
    requires_approval: bool
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


class TaskQueueError(Exception):
    pass


class PersistentTaskQueue:
    """Durable SQLite task queue for the local Navigator.

    This component stores intent and state only. It does not execute commands or
    models. A later Navigator loop will claim and process eligible tasks.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    requires_approval INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    last_error TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_claim
                    ON tasks(status, requires_approval, priority, created_at);
                CREATE TABLE IF NOT EXISTS task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def enqueue(
        self,
        *,
        title: str,
        goal: str,
        priority: int = 100,
        max_attempts: int = 3,
        requires_approval: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> TaskRecord:
        if not title.strip() or not goal.strip():
            raise TaskQueueError("title and goal are required")
        if max_attempts < 1:
            raise TaskQueueError("max_attempts must be at least 1")
        task_id = str(uuid.uuid4())
        now = self._now()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, title, goal, status, priority, attempts,
                    max_attempts, requires_approval, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'RECEIVED', ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title.strip(),
                    goal.strip(),
                    priority,
                    max_attempts,
                    int(requires_approval),
                    metadata_json,
                    now,
                    now,
                ),
            )
            self._append_event(connection, task_id, "TASK_ENQUEUED", {"status": "RECEIVED"})
        return self.get(task_id)

    def get(self, task_id: str) -> TaskRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise TaskQueueError(f"task not found: {task_id}")
        return self._to_record(row)

    def list_tasks(self, status: str | None = None, limit: int = 100) -> list[TaskRecord]:
        if limit < 1:
            raise TaskQueueError("limit must be positive")
        with self._connect() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM tasks ORDER BY priority ASC, created_at ASC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                self._validate_state(status)
                rows = connection.execute(
                    """
                    SELECT * FROM tasks WHERE status = ?
                    ORDER BY priority ASC, created_at ASC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        return [self._to_record(row) for row in rows]

    def transition(
        self,
        task_id: str,
        new_status: str,
        *,
        payload: dict[str, Any] | None = None,
        last_error: str | None = None,
    ) -> TaskRecord:
        self._validate_state(new_status)
        with self._connect() as connection:
            current = connection.execute(
                "SELECT status, attempts, max_attempts FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if current is None:
                raise TaskQueueError(f"task not found: {task_id}")
            if current["status"] in TERMINAL_STATES:
                raise TaskQueueError("terminal task cannot transition")
            attempts = int(current["attempts"])
            if new_status == "RETRYING":
                attempts += 1
                if attempts >= int(current["max_attempts"]):
                    new_status = "FAILED"
            now = self._now()
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, attempts = ?, last_error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (new_status, attempts, last_error, now, task_id),
            )
            self._append_event(
                connection,
                task_id,
                "TASK_TRANSITION",
                {"status": new_status, **(payload or {})},
            )
        return self.get(task_id)

    def approve(self, task_id: str) -> TaskRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise TaskQueueError(f"task not found: {task_id}")
            if row["status"] != "WAITING_APPROVAL":
                raise TaskQueueError("task is not waiting for approval")
            now = self._now()
            connection.execute(
                """
                UPDATE tasks
                SET requires_approval = 0, status = 'PLANNED', updated_at = ?
                WHERE task_id = ?
                """,
                (now, task_id),
            )
            self._append_event(connection, task_id, "TASK_APPROVED", {})
        return self.get(task_id)

    def events(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_type, payload_json, created_at
                FROM task_events WHERE task_id = ? ORDER BY event_id ASC
                """,
                (task_id,),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO task_events (task_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                task_id,
                event_type,
                json.dumps(payload, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    @staticmethod
    def _validate_state(status: str) -> None:
        if status not in TASK_STATES:
            raise TaskQueueError(f"invalid task state: {status}")

    @staticmethod
    def _to_record(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            title=row["title"],
            goal=row["goal"],
            status=row["status"],
            priority=int(row["priority"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            requires_approval=bool(row["requires_approval"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"]),
        )
