from __future__ import annotations
import argparse
import json
from local_relay_dispatcher_v0_2 import LocalRelayDispatcherV02


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime_root")
    parser.add_argument("--worker-id", default="WINDOW-01")
    args = parser.parse_args()
    dispatcher = LocalRelayDispatcherV02(args.runtime_root)
    print(json.dumps(dispatcher.scan_once(args.worker_id), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
