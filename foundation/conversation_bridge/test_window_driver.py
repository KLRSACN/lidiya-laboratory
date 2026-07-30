from __future__ import annotations

import unittest

from window_driver import (
    AllowlistedWindowDriver,
    CaptureSample,
    WindowCandidate,
    WindowDriverError,
)


class FakeBackend:
    def __init__(self, windows=None, captures=None):
        self.windows = list(windows or [])
        self.captures = list(captures or [])
        self.focused = None
        self.sent = []

    def list_windows(self):
        return list(self.windows)

    def focus(self, handle):
        self.focused = handle

    def send_text(self, handle, text):
        self.sent.append((handle, text))

    def capture(self, handle):
        if self.captures:
            return self.captures.pop(0)
        return CaptureSample(text="", generation_active=False)


class WindowDriverTests(unittest.TestCase):
    def test_selects_unique_chatgpt_window(self):
        backend = FakeBackend([
            WindowCandidate(1, "ChatGPT - Lidiya", "chrome.exe"),
            WindowCandidate(2, "YouTube", "chrome.exe"),
        ])
        selected = AllowlistedWindowDriver(backend).select_unique("chatgpt")
        self.assertEqual(selected.handle, 1)

    def test_rejects_ambiguous_windows(self):
        backend = FakeBackend([
            WindowCandidate(1, "ChatGPT A", "chrome.exe"),
            WindowCandidate(2, "ChatGPT B", "msedge.exe"),
        ])
        with self.assertRaisesRegex(WindowDriverError, "ambiguous"):
            AllowlistedWindowDriver(backend).select_unique("chatgpt")

    def test_rejects_wrong_process(self):
        backend = FakeBackend([WindowCandidate(1, "ChatGPT", "notepad.exe")])
        with self.assertRaisesRegex(WindowDriverError, "no allowlisted"):
            AllowlistedWindowDriver(backend).select_unique("chatgpt")

    def test_dry_run_never_focuses_or_sends(self):
        backend = FakeBackend([WindowCandidate(1, "Gemini", "chrome.exe")])
        driver = AllowlistedWindowDriver(backend)
        selected = driver.select_unique("gemini")
        result = driver.deliver(selected, "hello", dry_run=True)
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertIsNone(backend.focused)
        self.assertEqual(backend.sent, [])

    def test_live_delivery_uses_selected_handle(self):
        backend = FakeBackend([WindowCandidate(7, "Gemini", "chrome.exe")])
        driver = AllowlistedWindowDriver(backend)
        selected = driver.select_unique("gemini")
        result = driver.deliver(selected, "hello", dry_run=False)
        self.assertEqual(result["status"], "SENT")
        self.assertEqual(backend.focused, 7)
        self.assertEqual(backend.sent, [(7, "hello")])

    def test_capture_waits_for_stable_response(self):
        backend = FakeBackend(
            [WindowCandidate(1, "ChatGPT", "chrome.exe")],
            [
                CaptureSample("partial", True),
                CaptureSample("answer", False),
                CaptureSample("answer", False),
            ],
        )
        driver = AllowlistedWindowDriver(backend)
        selected = driver.select_unique("chatgpt")
        result = driver.capture_until_stable(selected)
        self.assertEqual(result["status"], "STABLE")
        self.assertEqual(result["text"], "answer")

    def test_capture_surfaces_platform_error(self):
        backend = FakeBackend(
            [WindowCandidate(1, "ChatGPT", "chrome.exe")],
            [CaptureSample("", False, "network error")],
        )
        driver = AllowlistedWindowDriver(backend)
        selected = driver.select_unique("chatgpt")
        result = driver.capture_until_stable(selected)
        self.assertEqual(result["status"], "PLATFORM_ERROR")


if __name__ == "__main__":
    unittest.main()
