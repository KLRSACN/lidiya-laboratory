from __future__ import annotations

import argparse
import json
from pathlib import Path

from local_relay_dispatcher import LocalRelayDispatcher


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-pass safe local relay worker stub")
    parser.add_argument("runtime_root", type=Path)
    parser.add_argument("--worker-id", default="WINDOW-01")
    args = parser.parse_args()
    dispatcher = LocalRelayDispatcher(args.runtime_root)
    result = dispatcher.scan_once(args.worker_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") not in {"FAILED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
