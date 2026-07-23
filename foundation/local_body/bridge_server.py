#!/usr/bin/env python3
"""Lidiya localhost-only, read-only evidence bridge.

Security properties:
- refuses non-loopback bind addresses;
- requires a token from a local environment variable;
- exposes GET endpoints only;
- reads only named JSON reports under pre-approved roots;
- never runs shell commands, installs software, or writes formal data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("LIDIYA_BRIDGE_CONFIG", ROOT / "approved_reports.json"))
HOST = os.environ.get("LIDIYA_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("LIDIYA_BRIDGE_PORT", "8765"))
TOKEN_ENV = os.environ.get("LIDIYA_BRIDGE_TOKEN_ENV", "LIDIYA_BRIDGE_TOKEN")
MAX_REPORT_BYTES = 5 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        raise RuntimeError(f"Missing approved report config: {CONFIG_PATH}")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("authorized") is not True:
        raise RuntimeError("Bridge config is not owner-authorized")
    roots = config.get("approved_roots") or []
    if not roots:
        raise RuntimeError("No approved roots configured")
    return config


def resolve_report(config: dict[str, Any], name: str) -> tuple[Path, str | None]:
    reports = config.get("reports") or {}
    if name not in reports:
        raise KeyError(name)
    entry = reports[name]
    path = Path(entry["path"]).expanduser().resolve(strict=True)
    roots = [Path(value).expanduser().resolve(strict=True) for value in config["approved_roots"]]
    if not any(is_under(path, root) for root in roots):
        raise PermissionError("Report is outside approved roots")
    if path.suffix.lower() != ".json":
        raise PermissionError("Only JSON reports are allowed")
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise PermissionError("Report exceeds size limit")
    return path, entry.get("expected_sha256")


class Handler(BaseHTTPRequestHandler):
    server_version = "LidiyaEvidenceBridge/0.1"

    def log_message(self, format: str, *args: object) -> None:
        # Minimal local log; Authorization headers and tokens are never logged.
        sys.stderr.write(f"{self.address_string()} {format % args}\n")

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self) -> bool:
        expected = os.environ.get(TOKEN_ENV, "")
        if len(expected) < 32:
            return False
        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not supplied.startswith(prefix):
            return False
        return hmac.compare_digest(supplied[len(prefix):], expected)

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path == "/health":
            self.send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "mode": "localhost_read_only",
                    "formal_system_write": False,
                    "shell_enabled": False,
                },
            )
            return

        if not self.authenticated():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return

        if path == "/capabilities":
            self.send_json(
                HTTPStatus.OK,
                {
                    "methods": ["GET"],
                    "endpoints": ["/health", "/capabilities", "/report/<approved-name>"],
                    "writes": False,
                    "shell": False,
                    "external_network": False,
                },
            )
            return

        if path.startswith("/report/"):
            name = path.removeprefix("/report/")
            try:
                config = load_config()
                report_path, expected_sha = resolve_report(config, name)
                actual_sha = sha256_file(report_path)
                if expected_sha and not hmac.compare_digest(actual_sha, expected_sha.upper()):
                    self.send_json(
                        HTTPStatus.CONFLICT,
                        {"error": "sha256_mismatch", "actual_sha256": actual_sha},
                    )
                    return
                payload = json.loads(report_path.read_text(encoding="utf-8"))
                self.send_json(
                    HTTPStatus.OK,
                    {
                        "name": name,
                        "sha256": actual_sha,
                        "size": report_path.stat().st_size,
                        "report": payload,
                    },
                )
            except KeyError:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "unknown_report"})
            except (PermissionError, RuntimeError, OSError, json.JSONDecodeError) as exc:
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "report_blocked", "detail": str(exc)})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        self.send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "read_only_bridge"})

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST


def main() -> int:
    if HOST not in {"127.0.0.1", "localhost", "::1"}:
        print("BLOCK: bridge host must be loopback only", file=sys.stderr)
        return 3
    token = os.environ.get(TOKEN_ENV, "")
    if len(token) < 32:
        print(f"BLOCK: {TOKEN_ENV} must be set locally with at least 32 characters", file=sys.stderr)
        return 4
    try:
        load_config()
    except Exception as exc:
        print(f"BLOCK: {exc}", file=sys.stderr)
        return 5

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Lidiya evidence bridge listening on http://{HOST}:{PORT} (read-only)")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
