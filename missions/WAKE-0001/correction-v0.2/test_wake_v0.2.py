from __future__ import annotations

import json
import tempfile
from pathlib import Path

import importlib.util
import sys

MODULE_PATH = Path(__file__).with_name("simulate_wake_v0.2.py")
spec = importlib.util.spec_from_file_location("simulate_wake_v0_2", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)
WakeWorkerV02 = module.WakeWorkerV02
checkpoint_hash = module.checkpoint_hash
make_trigger = module.make_trigger
sha256_bytes = module.sha256_bytes


def make_checkpoint(mission: str, token: str, step: int, result_hash=None, *, completed_steps=None):
    steps = ["ENTER_RUNNING", "ARTIFACT_PLAN_CONFIRMED", "RELAY_PREPARED", "RESET_TO_WAIT_TRIGGER"]
    cp = {
        "mission_id": mission,
        "token": token,
        "current_state": ["WAIT_TRIGGER", "RUNNING", "RUNNING", "RELAY_READY", "WAIT_TRIGGER"][step],
        "highest_progress_token": f"{mission}:{token}:P{step:04d}",
        "next_action": steps[step] if step < 4 else "NONE",
        "completed_steps": steps[:step] if completed_steps is None else completed_steps,
        "pending_steps": steps[step:],
        "result_hash": result_hash,
        "recoverable": True,
    }
    cp["checkpoint_hash"] = checkpoint_hash(cp)
    return cp


def run_tests():
    results = []

    def check(name, fn):
        try:
            fn()
            results.append({"name": name, "status": "PASS"})
        except Exception as exc:
            results.append({"name": name, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})

    with tempfile.TemporaryDirectory(prefix="wake_v02_tests_") as td:
        base = Path(td)

        def t1_first_run():
            w = WakeWorkerV02(base / "t1")
            r = w.run(make_trigger())
            assert r.status == "COMPLETED"
            assert r.progress_token.endswith("P0004")
            assert r.state == "WAIT_TRIGGER" and r.heartbeat == "READY"

        def t2_duplicate_same_hash():
            w = WakeWorkerV02(base / "t2")
            first = w.run(make_trigger())
            result_path = w.result_path("WAKE-0001", "BOOTSTRAP-0001")
            before = sha256_bytes(result_path.read_bytes())
            second = w.run(make_trigger())
            after = sha256_bytes(result_path.read_bytes())
            assert second.status == "DUPLICATE_COMPLETED"
            assert before == after == first.result_hash
            assert second.executed_steps == []

        def t3_different_token():
            w = WakeWorkerV02(base / "t3")
            assert w.run(make_trigger("TOKEN-A")).status == "COMPLETED"
            assert w.run(make_trigger("TOKEN-B")).status == "COMPLETED"
            state = json.loads(w.state_path.read_text())
            assert len(state["completed_assignments"]) == 2

        def t4_resume_p3_only_reset():
            w = WakeWorkerV02(base / "t4")
            cp = make_checkpoint("WAKE-0001", "BOOTSTRAP-0001", 3)
            r = w.run(make_trigger(), cp)
            assert r.status == "COMPLETED"
            assert r.executed_steps == ["RESET_TO_WAIT_TRIGGER"]

        def t5_resume_p4_no_rerun():
            w = WakeWorkerV02(base / "t5")
            trigger = make_trigger()
            first = w.run(trigger)
            cp = json.loads(w.checkpoint_path("WAKE-0001", "BOOTSTRAP-0001").read_text())
            state = json.loads(w.state_path.read_text())
            state["completed_assignments"].clear()
            w.state_path.write_text(json.dumps(state), encoding="utf-8")
            r = w.run(trigger, cp)
            assert r.status == "DUPLICATE_COMPLETED"
            assert r.executed_steps == []
            assert r.result_hash == first.result_hash

        def t6_progress_regression():
            w = WakeWorkerV02(base / "t6")
            cp = make_checkpoint("WAKE-0001", "BOOTSTRAP-0001", 3, completed_steps=["ENTER_RUNNING"])
            r = w.run(make_trigger(), cp)
            assert r.status == "BLOCKED"
            assert r.blocker == "PROGRESS_TOKEN_REGRESSION_OR_STEP_MISMATCH"

        def t7_checkpoint_identity_mismatch():
            w = WakeWorkerV02(base / "t7")
            cp = make_checkpoint("OTHER", "BOOTSTRAP-0001", 3)
            r = w.run(make_trigger(), cp)
            assert r.status == "BLOCKED" and r.blocker == "CHECKPOINT_IDENTITY_MISMATCH"

        def t8_bad_checkpoint_hash():
            w = WakeWorkerV02(base / "t8")
            cp = make_checkpoint("WAKE-0001", "BOOTSTRAP-0001", 3)
            cp["next_action"] = "TAMPERED"
            r = w.run(make_trigger(), cp)
            assert r.status == "BLOCKED" and r.blocker == "CHECKPOINT_HASH_MISMATCH"

        def t9_missing_field():
            w = WakeWorkerV02(base / "t9")
            trigger = make_trigger(); trigger.pop("EVIDENCE_REQUIRED")
            r = w.run(trigger)
            assert r.status.startswith("INVALID_TRIGGER_MISSING_FIELDS") and r.state == "WAIT_TRIGGER"

        def t10_wrong_target():
            w = WakeWorkerV02(base / "t10")
            trigger = make_trigger(); trigger["TARGET"] = "WORKER-02"
            r = w.run(trigger)
            assert r.status == "INVALID_TRIGGER_WRONG_TARGET"

        def t11_wrong_action():
            w = WakeWorkerV02(base / "t11")
            trigger = make_trigger(); trigger["ACTION"] = "STOP"
            r = w.run(trigger)
            assert r.status == "INVALID_TRIGGER_WRONG_ACTION"

        for name, fn in [
            ("normal_first_execution", t1_first_run),
            ("duplicate_same_mission_token_hash_unchanged", t2_duplicate_same_hash),
            ("different_token_executes_and_preserves_old", t3_different_token),
            ("recover_from_p0003_only_reset", t4_resume_p3_only_reset),
            ("recover_from_p0004_no_rerun", t5_resume_p4_no_rerun),
            ("progress_token_regression_rejected", t6_progress_regression),
            ("checkpoint_mission_token_mismatch_rejected", t7_checkpoint_identity_mismatch),
            ("bad_checkpoint_hash_blocked", t8_bad_checkpoint_hash),
            ("invalid_trigger_missing_field", t9_missing_field),
            ("invalid_trigger_wrong_target", t10_wrong_target),
            ("invalid_trigger_wrong_action", t11_wrong_action),
        ]:
            check(name, fn)

    summary = {
        "total": len(results),
        "passed": sum(r["status"] == "PASS" for r in results),
        "failed": sum(r["status"] == "FAIL" for r in results),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_tests())
