from eval_harness import evaluate
def test_guard_bypass_forces_failure():
    rows=[{"task":"gate","expected":{"human_gate":True}}]; out=evaluate(rows,[{"human_gate":False}]); assert out["safety_pass"] is False and out["hard_guard_failures"]
def test_metrics_structured():
    rows=[{"task":"route","expected":{"gear":"G1"}}]; out=evaluate(rows,[{"gear":"G1"}]); assert out["metrics"]["route"]["accuracy"]==1.0 and out["safety_pass"]
