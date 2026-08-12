from copy import deepcopy
try:
    from .gearbox_controller import select_gear
except ImportError:
    from gearbox_controller import select_gear

def predict(features):
    before=deepcopy(features)
    d=select_gear(risk=features["risk"],uncertainty=features["uncertainty"],evidence_quality=features["evidence_quality"],task_complexity=features["task_complexity"],reversibility=features["reversibility"],contradiction=features.get("contradiction",False),hard_safety_conflict=features.get("hard_safety_conflict",False),storage_pressure_ratio=features.get("storage_pressure_ratio",0.0),proposed_autonomy=features.get("proposed_autonomy",1)).to_dict()
    if features!=before: raise RuntimeError("baseline mutated input")
    return d
