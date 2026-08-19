import unittest

from self_test_trend import summarize_samples


class SelfTestTrendTests(unittest.TestCase):
    def _sample(self, duration, *, group="g1", successful=True, slow="t1"):
        return {
            "comparison_group": group,
            "successful": successful,
            "self_test_duration_seconds": duration,
            "slowest_tests": [{"test_id": slow, "duration_seconds": duration / 2}],
        }

    def test_no_samples_is_non_claiming(self):
        summary = summarize_samples([])
        self.assertEqual(summary["status"], "NO_SAMPLES")
        self.assertEqual(summary["comparable_sample_count"], 0)

    def test_only_exact_comparison_group_is_used(self):
        summary = summarize_samples([
            self._sample(1.0, group="old"),
            self._sample(0.2, group="new"),
            self._sample(0.3, group="new"),
        ])
        self.assertEqual(summary["comparison_group"], "new")
        self.assertEqual(summary["comparable_sample_count"], 2)
        self.assertEqual(summary["status"], "COLLECTING_BASELINE")

    def test_failed_samples_are_excluded(self):
        summary = summarize_samples([
            self._sample(10.0, successful=False),
            self._sample(0.2),
        ])
        self.assertEqual(summary["comparable_sample_count"], 1)
        self.assertEqual(summary["median_duration_seconds"], 0.2)

    def test_ten_samples_create_stable_diagnostic_baseline_without_speedup_claim(self):
        samples = [self._sample(value / 100.0) for value in range(10, 20)]
        summary = summarize_samples(samples)
        self.assertEqual(summary["status"], "STABLE_BASELINE_AVAILABLE")
        self.assertEqual(summary["comparable_sample_count"], 10)
        self.assertFalse(summary["speedup_claim_allowed"])
        self.assertFalse(summary["real_5min_runtime_live"])

    def test_recurring_slowest_test_is_counted(self):
        summary = summarize_samples([
            self._sample(0.1, slow="same"),
            self._sample(0.2, slow="same"),
            self._sample(0.3, slow="other"),
        ])
        self.assertEqual(summary["recurring_slowest_tests"][0]["test_id"], "same")
        self.assertEqual(summary["recurring_slowest_tests"][0]["appearance_count"], 2)


if __name__ == "__main__":
    unittest.main()
