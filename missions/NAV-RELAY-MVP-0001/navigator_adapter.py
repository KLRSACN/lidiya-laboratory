from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from relay_mvp import RelayStore
from relay_protocol import parse_relay_output


class NavigatorError(RuntimeError):
    pass


class PageLike(Protocol):
    def locator(self, selector: str) -> Any: ...


@dataclass(frozen=True)
class WindowRecord:
    window_id: str
    role: str
    debug_port: int
    marker: str


DEFAULT_SELECTORS = {
    "composer": "#prompt-textarea, textarea[data-testid='prompt-textarea'], div[contenteditable='true']",
    "send": "button[data-testid='send-button'], button[aria-label*='Send'], button[aria-label*='送出']",
    "stop": "button[data-testid='stop-button'], button[aria-label*='Stop'], button[aria-label*='停止']",
    "assistant_messages": "[data-message-author-role='assistant']",
}


class NavigatorAdapter:
    def __init__(
        self,
        store: RelayStore,
        stable_seconds: float = 3.0,
        poll_seconds: float = 0.5,
        response_timeout_seconds: float = 300.0,
    ) -> None:
        self.store = store
        self.stable_seconds = stable_seconds
        self.poll_seconds = poll_seconds
        self.response_timeout_seconds = response_timeout_seconds

    def get_window(self, window_id: str) -> WindowRecord:
        row = self.store.connection.execute(
            "SELECT window_id, role, debug_port, marker FROM windows WHERE window_id=?",
            (window_id,),
        ).fetchone()
        if row is None:
            raise NavigatorError(f"window is not registered: {window_id}")
        return WindowRecord(
            window_id=row["window_id"],
            role=row["role"],
            debug_port=int(row["debug_port"]),
            marker=row["marker"],
        )

    @staticmethod
    def _connect_playwright(port: int):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise NavigatorError(
                "Playwright is required. Run: pip install playwright && playwright install chromium"
            ) from exc
        manager = sync_playwright().start()
        try:
            browser = manager.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        except Exception:
            manager.stop()
            raise
        return manager, browser

    @staticmethod
    def _all_pages(browser: Any) -> list[Any]:
        pages: list[Any] = []
        for context in browser.contexts:
            pages.extend(context.pages)
        return pages

    def find_page(self, browser: Any, marker: str) -> Any:
        pages = self._all_pages(browser)
        if not pages:
            raise NavigatorError("no browser pages found on the CDP port")

        marker_lower = marker.lower()
        window_token = marker_lower.removeprefix("[lidiya:").removesuffix("]")
        chatgpt_pages: list[Any] = []

        # Prefer ChatGPT conversation pages whose title contains either the
        # full marker or its stable window token, such as WINDOW-01.
        for page in pages:
            try:
                url = page.url.lower()
                if not url.startswith("https://chatgpt.com/"):
                    continue

                chatgpt_pages.append(page)
                title = page.title().lower()
                if marker_lower in title or window_token in title:
                    return page
            except Exception:
                continue

        # Fallback only for ChatGPT pages whose title has not updated yet.
        for page in chatgpt_pages:
            try:
                body = page.locator("body").inner_text(timeout=2000).lower()
                if marker_lower in body:
                    return page
            except Exception:
                continue

        if len(chatgpt_pages) == 1:
            return chatgpt_pages[0]

        raise NavigatorError(f"no ChatGPT page contains marker: {marker}")

    @staticmethod
    def _first_visible(page: Any, selector: str) -> Any:
        locator = page.locator(selector)
        for index in range(locator.count()):
            item = locator.nth(index)
            try:
                if item.is_visible():
                    return item
            except Exception:
                continue
        raise NavigatorError(f"no visible element for selector: {selector}")

    def paste_and_send(self, page: Any, text: str) -> None:
        composer = self._first_visible(page, DEFAULT_SELECTORS["composer"])
        composer.click()
        try:
            composer.fill(text)
        except Exception:
            page.keyboard.press("Control+A")
            page.keyboard.type(text)

        try:
            self._first_visible(page, DEFAULT_SELECTORS["send"]).click()
        except NavigatorError:
            page.keyboard.press("Enter")

    @staticmethod
    def latest_assistant_text(page: Any) -> str:
        locator = page.locator(DEFAULT_SELECTORS["assistant_messages"])
        count = locator.count()
        if count == 0:
            return ""
        return locator.nth(count - 1).inner_text().strip()

    @staticmethod
    def is_generating(page: Any) -> bool:
        locator = page.locator(DEFAULT_SELECTORS["stop"])
        for index in range(locator.count()):
            try:
                if locator.nth(index).is_visible():
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def assistant_message_count(page: Any) -> int:
        return page.locator(DEFAULT_SELECTORS["assistant_messages"]).count()

    def wait_for_complete_response(self, page: Any, previous_count: int = 0) -> str:
        deadline = time.monotonic() + self.response_timeout_seconds
        stable_since: float | None = None
        last_text = ""

        while time.monotonic() < deadline:
            count = self.assistant_message_count(page)
            text = self.latest_assistant_text(page)
            generating = self.is_generating(page)

            if count > previous_count and text and text == last_text and not generating:
                if stable_since is None:
                    stable_since = time.monotonic()
                elif time.monotonic() - stable_since >= self.stable_seconds:
                    return text
            else:
                stable_since = None

            last_text = text
            time.sleep(self.poll_seconds)

        raise NavigatorError("response timeout")

    def deliver_one(self, target_window_id: str) -> dict[str, Any] | None:
        row = self.store.next_message(target_window_id)
        if row is None:
            return None

        manager: Any | None = None
        sent = False

        try:
            window = self.get_window(target_window_id)
            manager, browser = self._connect_playwright(window.debug_port)
            page = self.find_page(browser, window.marker)
            previous_count = self.assistant_message_count(page)
            self.paste_and_send(page, row["payload"])
            self.store.mark_delivered(row["message_id"])
            sent = True

            try:
                response = self.wait_for_complete_response(page, previous_count)
            except NavigatorError as exc:
                if str(exc) == "response timeout":
                    self.store.mark_timed_out(row["message_id"])
                else:
                    self.store.mark_failed(row["message_id"])
                raise
            except Exception:
                self.store.mark_failed(row["message_id"])
                raise

            self.store.mark_completed(row["message_id"])
            return {
                "message_id": row["message_id"],
                "target": target_window_id,
                "response": response,
            }
        except Exception:
            if not sent:
                self.store.mark_failed(row["message_id"])
            raise
        finally:
            # manager.stop() disconnects Playwright. Do not call browser.close(),
            # because Chrome is owned by the user and must stay open for later wakes.
            if manager is not None:
                manager.stop()

    def ingest_response(self, mission_id: str, source_window_id: str, response_text: str) -> str:
        envelope = parse_relay_output(response_text)
        return self.store.enqueue(mission_id, source_window_id, envelope)


def run_loop(
    db_path: str,
    window_ids: list[str],
    mission_id: str,
    interval_seconds: float,
    response_timeout_seconds: float = 300.0,
) -> None:
    store = RelayStore(db_path)
    adapter = NavigatorAdapter(
        store,
        response_timeout_seconds=response_timeout_seconds,
    )
    while True:
        handled = False
        for window_id in window_ids:
            try:
                result = adapter.deliver_one(window_id)
            except Exception as exc:
                handled = True
                print(
                    json.dumps(
                        {
                            "delivery_error": str(exc),
                            "window_id": window_id,
                        },
                        ensure_ascii=False,
                    )
                )
                continue

            if result is None:
                continue

            handled = True
            print(json.dumps(result, ensure_ascii=False))
            try:
                next_message_id = adapter.ingest_response(
                    mission_id=mission_id,
                    source_window_id=window_id,
                    response_text=result["response"],
                )
                print(json.dumps({"enqueued": next_message_id}, ensure_ascii=False))
            except Exception as exc:
                print(json.dumps({"response_not_routable": str(exc)}, ensure_ascii=False))
        if not handled:
            time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="CDP Navigator Adapter")
    parser.add_argument("--db", default="nav_relay_mvp.sqlite3")
    parser.add_argument("--mission-id", default="NAV-RELAY-MVP-0001")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=300.0,
        help="maximum seconds to wait for one ChatGPT response",
    )
    parser.add_argument("window_ids", nargs="+", help="registered relay window IDs")
    args = parser.parse_args()
    run_loop(
        args.db,
        args.window_ids,
        args.mission_id,
        args.interval,
        args.response_timeout,
    )


if __name__ == "__main__":
    main()
