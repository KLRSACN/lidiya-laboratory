from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class WindowDriverError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class WindowCandidate:
    handle: int
    title: str
    process_name: str
    visible: bool = True


@dataclass(frozen=True, slots=True)
class WindowSelection:
    handle: int
    platform: str
    title: str
    process_name: str


@dataclass(frozen=True, slots=True)
class CaptureSample:
    text: str
    generation_active: bool
    error_banner: str | None = None


class WindowBackend(Protocol):
    def list_windows(self) -> list[WindowCandidate]: ...
    def focus(self, handle: int) -> None: ...
    def send_text(self, handle: int, text: str) -> None: ...
    def capture(self, handle: int) -> CaptureSample: ...


@dataclass(frozen=True, slots=True)
class PlatformRule:
    platform: str
    title_tokens: tuple[str, ...]
    process_names: tuple[str, ...]


DEFAULT_RULES: tuple[PlatformRule, ...] = (
    PlatformRule("chatgpt", ("chatgpt",), ("chrome.exe", "msedge.exe")),
    PlatformRule("gemini", ("gemini",), ("chrome.exe", "msedge.exe")),
    PlatformRule("local", ("lidiya", "sillytavern", "openclaw"), ("chrome.exe", "msedge.exe", "python.exe")),
)


class AllowlistedWindowDriver:
    def __init__(self, backend: WindowBackend, rules: tuple[PlatformRule, ...] = DEFAULT_RULES) -> None:
        self.backend = backend
        self.rules = {rule.platform: rule for rule in rules}

    def select_unique(self, platform: str) -> WindowSelection:
        rule = self.rules.get(platform)
        if rule is None:
            raise WindowDriverError(f"unsupported platform: {platform}")
        matches: list[WindowCandidate] = []
        for candidate in self.backend.list_windows():
            title = candidate.title.casefold()
            process = candidate.process_name.casefold()
            if not candidate.visible:
                continue
            if process not in {name.casefold() for name in rule.process_names}:
                continue
            if not any(token.casefold() in title for token in rule.title_tokens):
                continue
            matches.append(candidate)
        if not matches:
            raise WindowDriverError(f"no allowlisted {platform} window found")
        if len(matches) != 1:
            raise WindowDriverError(f"ambiguous {platform} windows: {len(matches)}")
        selected = matches[0]
        return WindowSelection(selected.handle, platform, selected.title, selected.process_name)

    def deliver(self, selection: WindowSelection, text: str, *, dry_run: bool = True) -> dict[str, object]:
        if not text.strip():
            raise WindowDriverError("message must not be empty")
        if dry_run:
            return {
                "status": "DRY_RUN",
                "platform": selection.platform,
                "handle": selection.handle,
                "characters": len(text),
            }
        self.backend.focus(selection.handle)
        self.backend.send_text(selection.handle, text)
        return {
            "status": "SENT",
            "platform": selection.platform,
            "handle": selection.handle,
            "characters": len(text),
        }

    def capture_until_stable(self, selection: WindowSelection, *, max_samples: int = 8, stable_required: int = 2) -> dict[str, object]:
        if max_samples < 1 or stable_required < 1:
            raise WindowDriverError("sample limits must be positive")
        previous = None
        stable = 0
        latest: CaptureSample | None = None
        for sample_index in range(1, max_samples + 1):
            latest = self.backend.capture(selection.handle)
            if latest.error_banner:
                return {
                    "status": "PLATFORM_ERROR",
                    "samples": sample_index,
                    "error_banner": latest.error_banner,
                    "text": latest.text,
                }
            if latest.generation_active:
                stable = 0
                previous = latest.text
                continue
            if latest.text == previous:
                stable += 1
            else:
                previous = latest.text
                stable = 1
            if stable >= stable_required:
                return {
                    "status": "STABLE",
                    "samples": sample_index,
                    "stable_samples": stable,
                    "text": latest.text,
                }
        return {
            "status": "TIMEOUT",
            "samples": max_samples,
            "stable_samples": stable,
            "text": latest.text if latest else "",
        }
