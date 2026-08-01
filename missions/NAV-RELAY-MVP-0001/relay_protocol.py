from __future__ import annotations

import re
from dataclasses import dataclass


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class RelayEnvelope:
    target: str
    action: str
    payload: str
    wake_after_seconds: int | None = None


_TARGET_RE = re.compile(r"^\[TARGET:([A-Z0-9_-]+)\]$", re.MULTILINE)
_ACTION_RE = re.compile(r"^\[ACTION:([A-Z0-9_-]+)\]$", re.MULTILINE)
_WAKE_RE = re.compile(r"^\[WAKE_AFTER:(\d+)\]$", re.MULTILINE)
_PAYLOAD_RE = re.compile(
    r"\[RELAY_OUTPUT_BEGIN\]\s*(.*?)\s*\[RELAY_OUTPUT_END\]",
    re.DOTALL,
)


def parse_relay_output(text: str) -> RelayEnvelope:
    if "[RELAY_READY]" not in text:
        raise ProtocolError("missing [RELAY_READY]")

    target_match = _TARGET_RE.search(text)
    action_match = _ACTION_RE.search(text)
    payload_match = _PAYLOAD_RE.search(text)
    if not target_match:
        raise ProtocolError("missing target")
    if not action_match:
        raise ProtocolError("missing action")
    if not payload_match:
        raise ProtocolError("missing relay payload")

    wake_match = _WAKE_RE.search(text)
    wake_after = int(wake_match.group(1)) if wake_match else None
    if wake_after is not None and not 1 <= wake_after <= 3600:
        raise ProtocolError("wake interval must be 1..3600 seconds")

    payload = payload_match.group(1).strip()
    if not payload:
        raise ProtocolError("payload is empty")

    return RelayEnvelope(
        target=target_match.group(1),
        action=action_match.group(1),
        payload=payload,
        wake_after_seconds=wake_after,
    )
