from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

MIN_STABLE_SAMPLES = 10


def _p95(values: list[float]) -> float:
    if not values:
        raise ValueError("p95 requires at least one value")
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def summarize_samples(samples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(sample) for sample in samples]
    if not rows:
        return {
            "schema_version": "1.0",
            "status": "NO_SAMPLES",
            "comparable_sample_count": 0,
            "claim_boundary": "No timing sample is available; no performance conclusion is allowed.",
        }

    latest = rows[-1]
    comparison_group = str(latest.get("comparison_group", "")).strip()
    comparable = [
        row for row in rows
        if row.get("successful") is True
        and str(row.get("comparison_group", "")).strip() == comparison_group
        and isinstance(row.get("self_test_duration_seconds"), (int, float))
        and not isinstance(row.get("self_test_duration_seconds"), bool)
    ]
    durations = [float(row["self_test_duration_seconds"]) for row in comparable]
    slow_counter: Counter[str] = Counter()
    for row in comparable:
        for slow in row.get("slowest_tests", []):
            if isinstance(slow, Mapping):
                test_id = str(slow.get("test_id", "")).strip()
                if test_id:
                    slow_counter[test_id] += 1

    if not durations:
        return {
            "schema_version": "1.0",
            "status": "NO_COMPARABLE_SUCCESSFUL_SAMPLES",
            "comparison_group": comparison_group,
            "comparable_sample_count": 0,
            "claim_boundary": "No successful comparable timing sample is available; no performance conclusion is allowed.",
        }

    median = statistics.median(durations)
    p95 = _p95(durations)
    latest_duration = durations[-1]
    sample_count = len(durations)
    stable = sample_count >= MIN_STABLE_SAMPLES
    latest_vs_median_ratio = latest_duration / median if median > 0 else None

    recurring_slow = [
        {"test_id": test_id, "appearance_count": count, "appearance_ratio": round(count / sample_count, 4)}
        for test_id, count in slow_counter.most_common(10)
    ]

    if not stable:
        optimization_signal = "OBSERVE_ONLY_INSUFFICIENT_SAMPLE_COUNT"
    elif latest_duration > p95:
        optimization_signal = "REVIEW_PERSISTENT_REGRESSION_BEFORE_OPTIMIZING"
    else:
        optimization_signal = "NO_PERSISTENT_DURATION_REGRESSION_SIGNAL"

    return {
        "schema_version": "1.0",
        "status": "STABLE_BASELINE_AVAILABLE" if stable else "COLLECTING_BASELINE",
        "comparison_group": comparison_group,
        "minimum_stable_samples": MIN_STABLE_SAMPLES,
        "comparable_sample_count": sample_count,
        "latest_duration_seconds": round(latest_duration, 6),
        "median_duration_seconds": round(median, 6),
        "p95_duration_seconds": round(p95, 6),
        "min_duration_seconds": round(min(durations), 6),
        "max_duration_seconds": round(max(durations), 6),
        "latest_vs_median_ratio": round(latest_vs_median_ratio, 4) if latest_vs_median_ratio is not None else None,
        "recurring_slowest_tests": recurring_slow,
        "optimization_signal": optimization_signal,
        "speedup_claim_allowed": False,
        "real_5min_runtime_live": False,
        "p_base": "READ_ONLY_UNCHANGED",
        "claim_boundary": (
            "Trend statistics compare only successful samples with the exact same comparison_group. "
            "Even with >=10 samples they are optimization diagnostics, not proof of capability, speedup, "
            "Experience, formal adoption, or real always-on runtime."
        ),
    }


def load_samples(paths: Iterable[Path]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            samples.extend(dict(row) for row in payload if isinstance(row, Mapping))
        elif isinstance(payload, Mapping):
            samples.append(dict(payload))
        else:
            raise ValueError(f"unsupported timing payload in {path}")
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze comparable P0 self-test timing samples.")
    parser.add_argument("--sample", action="append", required=True, help="Timing JSON path; repeat for multiple samples.")
    parser.add_argument("--output", default="evidence/p0-self-test-trend.json")
    args = parser.parse_args()

    summary = summarize_samples(load_samples(Path(value) for value in args.sample))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
