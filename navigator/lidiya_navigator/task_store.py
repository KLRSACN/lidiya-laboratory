from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import TaskEnvelope


class JsonTaskStore:
    """以 JSON 保存任務，讓導航重啟後可繼續。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, task: TaskEnvelope) -> None:
        path = self.root / f"{task.task_id}.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(task), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def load(self, task_id: str) -> TaskEnvelope:
        path = self.root / f"{task_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"task not found: {task_id}")
        return TaskEnvelope(**json.loads(path.read_text(encoding="utf-8")))

    def exists(self, task_id: str) -> bool:
        return (self.root / f"{task_id}.json").exists()
