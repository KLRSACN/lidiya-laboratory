from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GuardDecision:
    allowed: bool
    reason: str


class Guardian:
    BLOCKED_TOKENS = (
        ".env",
        "id_rsa",
        "browser cookies",
        "ignore previous instructions",
        "disable security",
        "powershell -enc",
        "curl | sh",
    )

    def inspect_text(self, text: str) -> GuardDecision:
        normalized = text.lower()
        for token in self.BLOCKED_TOKENS:
            if token in normalized:
                return GuardDecision(False, f"blocked token: {token}")
        return GuardDecision(True, "no blocked pattern found")
