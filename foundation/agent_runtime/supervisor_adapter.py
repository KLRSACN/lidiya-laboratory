from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class SupervisorError(Exception):
    """Raised when the supervisor response or plan violates runtime policy."""


@dataclass(frozen=True)
class SupervisorPlan:
    diagnosis: str
    retry: bool
    steps: list[dict[str, Any]]
    notes: str


Transport = Callable[[str, dict[str, Any], float], dict[str, Any]]


class HermesSupervisorAdapter:
    """Calls an Ollama-hosted Hermes model and validates its structured plan.

    The adapter never executes tools. It only returns a policy-checked plan to the
    Home Bridge runtime. Execution remains under the existing tool dispatcher.
    """

    def __init__(
        self,
        *,
        root: Path,
        allowed_tools: list[str],
        model: str = "hermes3:latest",
        endpoint: str = "http://127.0.0.1:11434/api/chat",
        timeout_seconds: float = 90.0,
        max_plan_steps: int = 6,
        transport: Transport | None = None,
    ) -> None:
        self.root = root.resolve()
        self.allowed_tools = set(allowed_tools)
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_plan_steps = max_plan_steps
        self.transport = transport or self._http_transport

    def propose(self, escalation: dict[str, Any]) -> SupervisorPlan:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "keep_alive": "2m",
            "options": {"temperature": 0.1, "num_predict": 900},
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(escalation, ensure_ascii=False, indent=2),
                },
            ],
        }
        response = self.transport(self.endpoint, payload, self.timeout_seconds)
        content = self._extract_content(response)
        try:
            raw_plan = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SupervisorError(f"supervisor returned invalid JSON: {exc}") from exc
        return self._validate_plan(raw_plan)

    def _system_prompt(self) -> str:
        tools = ", ".join(sorted(self.allowed_tools))
        return (
            "You are the bounded Hermes supervisor for Lidiya Home Bridge. "
            "Diagnose a failed task and return JSON only. Never execute tools. "
            "Never request shell, credentials, system writes, permanent deletion, "
            "or external publishing. Allowed tools: "
            f"{tools}. Output schema: "
            '{"diagnosis":"string","retry":true|false,"steps":['
            '{"tool":"allowed.tool","arguments":{}}],"notes":"string"}. '
            "Use at most the necessary steps. All file paths must stay inside the "
            "autonomous zone and should be relative paths."
        )

    @staticmethod
    def _extract_content(response: dict[str, Any]) -> str:
        message = response.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise SupervisorError("Ollama response missing message.content")
        return message["content"].strip()

    def _validate_plan(self, raw: Any) -> SupervisorPlan:
        if not isinstance(raw, dict):
            raise SupervisorError("plan must be a JSON object")
        diagnosis = raw.get("diagnosis")
        retry = raw.get("retry")
        steps = raw.get("steps")
        notes = raw.get("notes", "")
        if not isinstance(diagnosis, str) or not diagnosis.strip():
            raise SupervisorError("diagnosis must be a non-empty string")
        if not isinstance(retry, bool):
            raise SupervisorError("retry must be boolean")
        if not isinstance(steps, list):
            raise SupervisorError("steps must be a list")
        if len(steps) > self.max_plan_steps:
            raise SupervisorError("plan exceeds max_plan_steps")
        if not isinstance(notes, str):
            raise SupervisorError("notes must be a string")
        if not retry and steps:
            raise SupervisorError("retry=false requires an empty steps list")

        validated: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise SupervisorError(f"step {index} must be an object")
            tool = step.get("tool")
            arguments = step.get("arguments", {})
            if tool not in self.allowed_tools:
                raise SupervisorError(f"step {index} tool not allowed: {tool}")
            if not isinstance(arguments, dict):
                raise SupervisorError(f"step {index} arguments must be an object")
            self._validate_paths(arguments)
            validated.append({"tool": tool, "arguments": arguments})

        return SupervisorPlan(
            diagnosis=diagnosis.strip(),
            retry=retry,
            steps=validated,
            notes=notes.strip(),
        )

    def _validate_paths(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in {"path", "source", "destination", "root", "file"}:
                    self._validate_path_value(child)
                else:
                    self._validate_paths(child)
        elif isinstance(value, list):
            for child in value:
                self._validate_paths(child)

    def _validate_path_value(self, value: Any) -> None:
        if not isinstance(value, str):
            raise SupervisorError("path-like arguments must be strings")
        candidate = Path(value)
        resolved = candidate.resolve() if candidate.is_absolute() else (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise SupervisorError(f"path outside autonomous zone: {value}")

    @staticmethod
    def _http_transport(endpoint: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                decoded = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise SupervisorError(f"Ollama request failed: {exc}") from exc
        try:
            data = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise SupervisorError(f"Ollama returned invalid JSON envelope: {exc}") from exc
        if not isinstance(data, dict):
            raise SupervisorError("Ollama response envelope must be an object")
        return data
