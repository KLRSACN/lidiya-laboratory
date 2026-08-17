import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name, relpath):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


wind_secretary = load_module("wind_secretary", "self_repair/wind_secretary.py")
predictive_nav = load_module("predictive_navigator_v2", "navigation/predictive_navigator_v2.py")


def base_snapshot():
    return {
        "continuity": {
            "home_read_ok": True,
            "mission_read_ok": True,
            "self_backup_read_ok": True,
            "wake_receipt_read_ok": True,
        },
        "runtime": {
            "context_load_factor": 1.0,
            "active_item_count": 8,
            "stale_ref_count": 0,
            "waste_count": 0,
            "duplicate_ratio": 0.0,
            "tool_failure_streak": 0,
            "web_failure_streak": 0,
            "window_age_hours": 1,
        },
        "browser": {
            "all_pages_unreachable": False,
            "ui_frozen": False,
            "blank_or_endless_loading": False,
            "websocket_error_count": 0,
        },
        "route": {
            "route_drift": False,
            "formal_role_task_mismatch": False,
        },
        "scheduler": {
            "formal_role_task_mismatch": False,
            "prompt_route_drift": False,
        },
        "research": {"unresolved_critical_count": 0},
    }


class WindSecretaryTests(unittest.TestCase):
    def test_green_state(self):
        r = wind_secretary.assess(base_snapshot())
        self.assertEqual(r.risk_level, "GREEN")
        self.assertFalse(r.should_pre_save)
        self.assertTrue(r.formal_authority_untouched)

    def test_extreme_long_window_pressure(self):
        s = base_snapshot()
        s["runtime"]["context_load_factor"] = 5.2
        s["runtime"]["window_age_hours"] = 12
        s["runtime"]["web_failure_streak"] = 3
        r = wind_secretary.assess(s)
        self.assertIn(r.risk_level, {"ORANGE", "RED"})
        self.assertTrue(r.should_pre_save)
        self.assertIn("EXTREME_CONTEXT_PRESSURE", r.predicted_failure_modes)
        self.assertIn("NAVIGATOR_RISK_ESCALATION", r.preemptive_actions)

    def test_ui_transport_failure_prepares_rebind_not_identity_replacement(self):
        s = base_snapshot()
        s["browser"]["all_pages_unreachable"] = True
        r = wind_secretary.assess(s)
        self.assertEqual(r.risk_level, "RED")
        self.assertTrue(r.should_request_same_slot_rebind)
        self.assertIn("SAME_SLOT_REBIND_REQUEST", r.preemptive_actions)
        self.assertTrue(r.formal_authority_untouched)

    def test_missing_home_is_red(self):
        s = base_snapshot()
        s["continuity"]["home_read_ok"] = False
        r = wind_secretary.assess(s)
        self.assertEqual(r.risk_level, "RED")
        self.assertIn("DURABLE_AUTHORITY_READ_FAILURE", r.predicted_failure_modes)


class PredictiveNavigatorTests(unittest.TestCase):
    def test_normal_forecast(self):
        r = predictive_nav.predict(base_snapshot())
        self.assertEqual(r.system_state, "NORMAL_WITH_FORECAST")
        self.assertTrue(r.recovery_anchor_required)

    def test_predicts_window_failure_before_total_loss(self):
        s = base_snapshot()
        s["runtime"]["context_load_factor"] = 4.0
        s["runtime"]["window_age_hours"] = 10
        s["runtime"]["web_failure_streak"] = 2
        r = predictive_nav.predict(s)
        events = {x.event: x for x in r.predictions}
        self.assertIn(events["WINDOW_UI_OR_SESSION_DEGRADATION"].probability_band, {"HIGH", "VERY_HIGH"})
        self.assertIn("SAVE_W01_AND_W07_LATEST_CHECKPOINTS", r.immediate_actions)

    def test_role_mismatch_preempts_gear_dropout(self):
        s = base_snapshot()
        s["scheduler"]["formal_role_task_mismatch"] = True
        r = predictive_nav.predict(s)
        events = {x.event: x for x in r.predictions}
        self.assertIn(events["WORKER_ROUTE_OR_GEAR_DROPOUT"].probability_band, {"HIGH", "VERY_HIGH"})
        self.assertIn("PRECHECK_EXISTING_TASK_ROUTE_AND_SAME_SLOT_REBIND", r.immediate_actions)

    def test_missing_recovery_anchor_blocks_new_load(self):
        s = base_snapshot()
        s["continuity"]["self_backup_read_ok"] = False
        r = predictive_nav.predict(s)
        self.assertIn("REBUILD_RECOVERY_ANCHORS_BEFORE_NEW_RESEARCH_LOAD", r.immediate_actions)

    def test_browser_cookie_deletion_never_autonomous(self):
        r = predictive_nav.predict(base_snapshot())
        self.assertIn("AUTOMATIC_BROWSER_COOKIE_OR_SITE_DATA_DELETION", r.blocked_actions)


if __name__ == "__main__":
    unittest.main()
