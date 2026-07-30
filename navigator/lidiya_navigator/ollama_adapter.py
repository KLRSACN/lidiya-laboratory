from __future__ import annotations

import json
from urllib import error, request

from .adapters import ModelAdapter
from .models import ModelReply, TaskEnvelope


class OllamaAdapter(ModelAdapter):
    """透過本機 Ollama HTTP API 搭載任意相容模型。"""

    def __init__(self, model: str, endpoint: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.endpoint = endpoint.rstrip("/")

    def health_check(self) -> bool:
        try:
            with request.urlopen(f"{self.endpoint}/api/tags", timeout=3) as response:
                return response.status == 200
        except (OSError, error.URLError):
            return False

    def generate(self, task: TaskEnvelope, prompt: str) -> ModelReply:
        instruction = (
            "你是搭載於 Lidiya Navigator 的模型。"
            "請完成任務並在最後一行只輸出 STATUS:CONTINUE 或 STATUS:COMPLETED。\n"
            f"任務：{task.goal}\n"
            f"完成條件：{task.completion_criteria}\n"
            f"目前輪次：{task.turn_count}/{task.max_turns}\n"
            f"訊息：{prompt}"
        )
        payload = json.dumps({"model": self.model, "prompt": instruction, "stream": False}).encode("utf-8")
        req = request.Request(
            f"{self.endpoint}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        message = str(body.get("response", "")).strip()
        completed = message.endswith("STATUS:COMPLETED")
        return ModelReply(message=message, completed=completed, evidence=[f"ollama:{self.model}"])
