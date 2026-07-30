from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WakeLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, task_id: str, data: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "task_id": task_id,
            "data": data,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
