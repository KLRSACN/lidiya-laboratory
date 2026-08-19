from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import unittest
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SUITE_MODULES = (
    ("gearbox_v1", "evolution.test_gearbox_controller"),
    ("gearbox_v2", "evolution.test_gearbox_controller_v2"),
    ("gearbox_v2_1", "evolution.test_gearbox_controller_v2_1"),
    ("always_on_runtime", "evolution.local_command_tower.test_always_on_runtime"),
    ("self_test_trend", "evolution.test_self_test_trend"),
)


class TimedTextTestResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self._started: dict[str, float] = {}
        self.test_durations: list[dict[str, Any]] = []

    def startTest(self, test):
        self._started[test.id()] = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        started = self._started.pop(test.id(), None)
        if started is not None:
            self.test_durations.append({
                "test_id": test.id(),
                "duration_seconds": round(time.perf_counter() - started, 6),
            })
        super().stopTest(test)


def _suite_name(test_id: str) -> str:
    for suite_name, module_name in SUITE_MODULES:
        if test_id.startswith(module_name + "."):
            return suite_name
    return "unknown"


def _iter_test_ids(suite: unittest.TestSuite) -> Iterable[str]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_test_ids(item)
        else:
            yield item.id()


def run(output: Path, slowest_count: int) -> int:
    total_started = time.perf_counter()
    load_started = time.perf_counter()
    aggregate = unittest.TestSuite()
    test_ids: list[str] = []
    for _, module_name in SUITE_MODULES:
        loaded = unittest.defaultTestLoader.loadTestsFromName(module_name)
        test_ids.extend(_iter_test_ids(loaded))
        aggregate.addTests(loaded)
    load_seconds = time.perf_counter() - load_started

    canonical_ids = sorted(test_ids)
    suite_signature = hashlib.sha256("\n".join(canonical_ids).encode("utf-8")).hexdigest()
    python_series = f"{sys.version_info.major}.{sys.version_info.minor}"
    comparison_group = f"{suite_signature}:py{python_series}"

    test_started = time.perf_counter()
    runner = unittest.TextTestRunner(verbosity=2, resultclass=TimedTextTestResult)
    result: TimedTextTestResult = runner.run(aggregate)
    test_seconds = time.perf_counter() - test_started
    total_seconds = time.perf_counter() - total_started

    suite_seconds: dict[str, float] = defaultdict(float)
    for row in result.test_durations:
        suite_seconds[_suite_name(row["test_id"])] += float(row["duration_seconds"])

    slowest = sorted(
        result.test_durations,
        key=lambda row: float(row["duration_seconds"]),
        reverse=True,
    )[: max(0, slowest_count)]

    commit_sha = os.environ.get("GITHUB_SHA")
    run_id = os.environ.get("GITHUB_RUN_ID")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT")
    sample_identity = json.dumps(
        {
            "commit_sha": commit_sha,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "comparison_group": comparison_group,
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    evidence = {
        "schema_version": "1.1",
        "evidence_type": "p0_candidate_self_test_duration",
        "mission_id": "LCR-EVOLUTION-0005",
        "sample_id": hashlib.sha256(sample_identity.encode("utf-8")).hexdigest(),
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit_sha": commit_sha,
        "ref_name": os.environ.get("GITHUB_REF_NAME"),
        "github_run_id": run_id,
        "github_run_attempt": run_attempt,
        "python_version": platform.python_version(),
        "python_series": python_series,
        "runner_system": platform.system(),
        "runner_machine": platform.machine(),
        "suite_signature_sha256": suite_signature,
        "comparison_group": comparison_group,
        "test_ids": canonical_ids,
        "timing_clock": "time.perf_counter_monotonic",
        "timing_scope": "candidate_ci_self_test_only",
        "timing_policy": "OBSERVATIONAL_ONLY_NO_SPEEDUP_OR_PROMOTION_CLAIM",
        "test_count": result.testsRun,
        "successful": result.wasSuccessful(),
        "failure_count": len(result.failures),
        "error_count": len(result.errors),
        "skipped_count": len(result.skipped),
        "load_duration_seconds": round(load_seconds, 6),
        "self_test_duration_seconds": round(test_seconds, 6),
        "runner_total_duration_seconds": round(total_seconds, 6),
        "per_suite_duration_seconds": {
            name: round(seconds, 6) for name, seconds in sorted(suite_seconds.items())
        },
        "slowest_tests": slowest,
        "real_5min_runtime_live": False,
        "runtime_maintenance_counts_as_experience": False,
        "p_base": "READ_ONLY_UNCHANGED",
        "formal_state_mutation": False,
        "claim_boundary": (
            "This duration measures bounded candidate self-test execution only. Samples are comparable only "
            "within the same comparison_group. It is not real always-on runtime evidence, capability proof, "
            "Experience, or LCR-C verification."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SELF_TEST_DURATION_SECONDS={evidence['self_test_duration_seconds']}")
    print(f"SELF_TEST_COUNT={evidence['test_count']}")
    print(f"SELF_TEST_COMPARISON_GROUP={comparison_group}")
    print(output.read_text(encoding="utf-8"))
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run exact-current P0 tests with monotonic duration evidence.")
    parser.add_argument(
        "--output",
        default="evidence/p0-self-test-duration.json",
        help="JSON evidence output path relative to mission root.",
    )
    parser.add_argument("--slowest-count", type=int, default=10)
    args = parser.parse_args()
    return run(Path(args.output), args.slowest_count)


if __name__ == "__main__":
    raise SystemExit(main())
