import json
from pathlib import Path
from eval_harness import evaluate

MANIFEST_PATH = Path(__file__).with_name("EXPERT_DATASET_MANIFEST.json")
HARD_GUARD_FIELDS=("human_gate","guard_status","protected_delete","unsafe_action")

def adversarial_rows():
    m=json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return [{"task":x["record"]["task"],"expected":x["record"]["expected"]} for x in m["rows"] if x["split"]=="adversarial"]

def test_guard_bypass_forces_failure():
    rows=[{"task":"gate","expected":{"human_gate":True}}]; out=evaluate(rows,[{"human_gate":False}]); assert out["safety_pass"] is False and out["hard_guard_failures"]
def test_metrics_structured():
    rows=[{"task":"route","expected":{"gear":"G1"}}]; out=evaluate(rows,[{"gear":"G1"}]); assert out["metrics"]["route"]["accuracy"]==1.0 and out["safety_pass"]

def test_materialized_adversarial_fixtures_pass_when_guards_match():
    rows=adversarial_rows(); predictions=[dict(x["expected"]) for x in rows]; out=evaluate(rows,predictions)
    assert len(rows)==7 and out["safety_pass"] is True and out["hard_guard_failures"]==[]
    assert all(out["metrics"][x["task"]]["accuracy"]==1.0 for x in rows)

def test_every_materialized_adversarial_guard_bypass_forces_safety_failure():
    rows=adversarial_rows()
    for i,row in enumerate(rows):
        predictions=[dict(x["expected"]) for x in rows]
        guard=next(k for k in HARD_GUARD_FIELDS if k in row["expected"])
        original=row["expected"][guard]
        predictions[i][guard]=(not original) if isinstance(original,bool) else "BYPASSED"
        out=evaluate(rows,predictions)
        assert out["safety_pass"] is False
        assert any(f["index"]==i and f["field"]==guard for f in out["hard_guard_failures"])
