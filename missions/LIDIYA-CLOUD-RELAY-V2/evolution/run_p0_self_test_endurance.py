from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _round_or_none(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def run_endurance(
    output: Path,
    target_duration_seconds: float,
    min_rounds: int,
    max_rounds: int,
    slowest_count: int,
) -> int:
    if target_duration_seconds <= 0:
        raise ValueError("target_duration_seconds must be > 0")
    if min_rounds <= 0:
        raise ValueError("min_rounds must be > 0")
    if max_rounds < min_rounds:
        raise ValueError("max_rounds must be >= min_rounds")

    session_started = time.perf_counter()
    rounds: list[dict[str, Any]] = []
    stop_reason = "UNKNOWN"
    success = True

    mission_root = Path(__file__).resolve().parents[1]
    single_runner = mission_root / "evolution" / "run_p0_self_test.py"

    with tempfile.TemporaryDirectory(prefix="lidiya-p0-endurance-") as tmp:
        tmp_root = Path(tmp)
        while len(rounds) < max_rounds:
            round_index = len(rounds) + 1
            round_output = tmp_root / f"round-{round_index:04d}.json"
            wall_started = time.perf_counter()
            completed = subprocess.run(
                [
                    sys.executable,
                    str(single_runner),
                    "--output",
                    str(round_output),
                    "--slowest-count",
                    str(max(0, slowest_count)),
                ],
                cwd=mission_root,
                env=os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            wall_seconds = time.perf_counter() - wall_started

            timing: dict[str, Any]
            if round_output.exists():
                timing = json.loads(round_output.read_text(encoding="utf-8"))
            else:
                timing = {
                    "successful": False,
                    "test_count": 0,
                    "self_test_duration_seconds": None,
                    "runner_total_duration_seconds": None,
                    "comparison_group": None,
                    "suite_signature_sha256": None,
                    "claim_boundary": "Round timing artifact missing; no timing or success claim allowed.",
                }

            round_success = bool(timing.get("successful")) and completed.returncode == 0
            rounds.append(
                {
                    "round": round_index,
                    "successful": round_success,
                    "returncode": completed.returncode,
                    "wall_duration_seconds": round(wall_seconds, 6),
                    "self_test_duration_seconds": timing.get("self_test_duration_seconds"),
                    "runner_total_duration_seconds": timing.get("runner_total_duration_seconds"),
                    "test_count": timing.get("test_count"),
                    "comparison_group": timing.get("comparison_group"),
                    "suite_signature_sha256": timing.get("suite_signature_sha256"),
                    "failure_count": timing.get("failure_count"),
                    "error_count": timing.get("error_count"),
                    "skipped_count": timing.get("skipped_count"),
                    "slowest_tests": timing.get("slowest_tests", []),
                }
            )

            if not round_success:
                success = False
                stop_reason = "FIRST_TEST_FAILURE_FAIL_FAST"
                break

            elapsed = time.perf_counter() - session_started
            if len(rounds) >= min_rounds and elapsed >= target_duration_seconds:
                stop_reason = "TARGET_DURATION_REACHED"
                break
        else:
            stop_reason = "MAX_ROUNDS_REACHED"

    session_seconds = time.perf_counter() - session_started
    self_test_durations = [
        float(row["self_test_duration_seconds"])
        for row in rounds
        if row.get("self_test_duration_seconds") is not None
    ]
    runner_durations = [
        float(row["runner_total_duration_seconds"])
        for row in rounds
        if row.get("runner_total_duration_seconds") is not None
    ]
    wall_durations = [float(row["wall_duration_seconds"]) for row in rounds]
    test_counts = [int(row["test_count"]) for row in rounds if row.get("test_count") is not None]
    comparison_groups = [str(row["comparison_group"]) for row in rounds if row.get("comparison_group")]
    comparison_group_consistent = bool(comparison_groups) and len(set(comparison_groups)) == 1
    comparison_group = comparison_groups[0] if comparison_group_consistent else None

    midpoint = len(self_test_durations) // 2
    first_half = self_test_durations[:midpoint] if midpoint else self_test_durations
    second_half = self_test_durations[midpoint:] if midpoint else self_test_durations
    first_median = statistics.median(first_half) if first_half else None
    second_median = statistics.median(second_half) if second_half else None
    median_drift_ratio = None
    if first_median is not None and second_median is not None and first_median > 0:
        median_drift_ratio = (second_median - first_median) / first_median

    runner_sum = sum(runner_durations)
    evidence = {
        "schema_version": "1.1",
        "evidence_type": "p0_candidate_self_test_endurance_duration",
        "mission_id": "LCR-EVOLUTION-0005",
        "commit_sha": os.environ.get("GITHUB_SHA"),
        "ref_name": os.environ.get("GITHUB_REF_NAME"),
        "timing_clock": "time.perf_counter_monotonic",
        "timing_scope": "bounded_candidate_ci_self_test_endurance_only",
        "timing_policy": "OBSERVATIONAL_ONLY_NO_SPEEDUP_OR_PROMOTION_CLAIM",
        "comparison_group": comparison_group,
        "comparison_group_consistent": comparison_group_consistent,
        "target_duration_seconds": round(target_duration_seconds, 6),
        "minimum_rounds": min_rounds,
        "maximum_rounds": max_rounds,
        "session_duration_seconds": round(session_seconds, 6),
        "target_duration_reached": session_seconds >= target_duration_seconds,
        "stop_reason": stop_reason,
        "rounds_completed": len(rounds),
        "successful": success and bool(rounds) and comparison_group_consistent,
        "successful_rounds": sum(1 for row in rounds if row["successful"]),
        "test_count_consistent": len(set(test_counts)) <= 1 if test_counts else False,
        "tests_per_round": test_counts[0] if test_counts and len(set(test_counts)) == 1 else None,
        "cumulative_self_test_duration_seconds": round(sum(self_test_durations), 6),
        "cumulative_runner_duration_seconds": round(runner_sum, 6),
        "session_minus_runner_duration_seconds": round(max(0.0, session_seconds - runner_sum), 6),
        "round_self_test_duration_seconds": {
            "min": _round_or_none(min(self_test_durations) if self_test_durations else None),
            "median": _round_or_none(statistics.median(self_test_durations) if self_test_durations else None),
            "p95_nearest_rank": _round_or_none(_percentile(self_test_durations, 0.95)),
            "max": _round_or_none(max(self_test_durations) if self_test_durations else None),
            "first_half_median": _round_or_none(first_median),
            "second_half_median": _round_or_none(second_median),
            "median_drift_ratio": _round_or_none(median_drift_ratio),
        },
        "round_wall_duration_seconds": {
            "min": _round_or_none(min(wall_durations) if wall_durations else None),
            "median": _round_or_none(statistics.median(wall_durations) if wall_durations else None),
            "p95_nearest_rank": _round_or_none(_percentile(wall_durations, 0.95)),
            "max": _round_or_none(max(wall_durations) if wall_durations else None),
        },
        "runner_fraction_of_session": _round_or_none(_safe_ratio(runner_sum, session_seconds)),
        "rounds": rounds,
        "optimization_boundary": {
            "adaptive_stop_enabled": False,
            "reason": "Collect comparable evidence first; numeric stability/drift thresholds remain TEST_REQUIRED.",
            "self_test_duration_is_experience": False,
            "self_test_duration_is_capability_proof": False,
            "self_test_duration_is_real_always_on_runtime": False,
        },
        "real_5min_runtime_live": False,
        "runtime_maintenance_counts_as_experience": False,
        "p_base": "READ_ONLY_UNCHANGED",
        "formal_state_mutation": False,
        "formal_c_verification": "NOT_CLAIMED",
        "claim_boundary": (
            "This is bounded candidate self-test endurance timing only. All rounds must share one comparison_group. "
            "It measures repeated regression stability and timing drift; it is not real always-on runtime evidence, "
            "capability proof, Experience, or LCR-C verification."
        ),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SELF_TEST_ENDURANCE_SECONDS={evidence['session_duration_seconds']}")
    print(f"SELF_TEST_ENDURANCE_ROUNDS={evidence['rounds_completed']}")
    print(f"SELF_TEST_ENDURANCE_STOP_REASON={evidence['stop_reason']}")
    print(f"SELF_TEST_ENDURANCE_COMPARISON_GROUP={evidence['comparison_group']}")
    print(output.read_text(encoding="utf-8"))
    return 0 if evidence["successful"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded repeated P0 candidate regressions and emit endurance-duration evidence."
    )
    parser.add_argument(
        "--output",
        default="evidence/p0-self-test-endurance.json",
        help="JSON evidence output path relative to mission root unless absolute.",
    )
    parser.add_argument("--target-duration-seconds", type=float, default=15.0)
    parser.add_argument("--min-rounds", type=int, default=8)
    parser.add_argument("--max-rounds", type=int, default=120)
    parser.add_argument("--slowest-count", type=int, default=5)
    args = parser.parse_args()
    return run_endurance(
        Path(args.output),
        args.target_duration_seconds,
        args.min_rounds,
        args.max_rounds,
        args.slowest_count,
    )


if __name__ == "__main__":
    raise SystemExit(main())
