from __future__ import annotations
import hashlib, json, math
from typing import Dict, Mapping, Any

DIMENSIONS=(
    "W_salience","W_emotion","W_self","W_relation","W_goal","W_loss","W_irreversible",
    "W_novelty","W_recurrence","W_identity","W_behavior","W_motivation","W_confidence"
)
POLICY_VERSION="MEMORY-WEIGHT-LAB-0.1-CANDIDATE"
DEFAULT_MAX_ABS_DELTA=0.25  # TEST_REQUIRED experimental bound, not canonical personality truth.

class WeightLabError(ValueError): pass

def _canonical(value: Any) -> str:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()

def _finite_number(v: Any) -> float:
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(float(v)):
        raise WeightLabError("weight must be finite numeric")
    return float(v)

def validate_base(base: Mapping[str,Any]) -> Dict[str,float]:
    if set(base) != set(DIMENSIONS): raise WeightLabError("base must contain exactly the 13 known dimensions")
    out={}
    for k in DIMENSIONS:
        v=_finite_number(base[k])
        if not 0.0 <= v <= 1.0: raise WeightLabError("base weight out of [0,1]")
        out[k]=v
    return out

def validate_overlay(overlay: Mapping[str,Any],max_abs_delta: float=DEFAULT_MAX_ABS_DELTA) -> Dict[str,float]:
    limit=_finite_number(max_abs_delta)
    if limit <= 0 or limit > 1: raise WeightLabError("invalid overlay limit")
    unknown=set(overlay)-set(DIMENSIONS)
    if unknown: raise WeightLabError("unknown dimensions: "+",".join(sorted(unknown)))
    out={}
    for k,v0 in overlay.items():
        v=_finite_number(v0)
        if abs(v) > limit: raise WeightLabError("overlay delta exceeds experimental bound")
        out[k]=v
    return out

def apply_overlay(base: Mapping[str,Any],overlay: Mapping[str,Any],*,max_abs_delta: float=DEFAULT_MAX_ABS_DELTA,experiment_id: str="EXP") -> Dict[str,Any]:
    clean_base=validate_base(base); clean_overlay=validate_overlay(overlay,max_abs_delta)
    base_before=dict(clean_base)
    effective={k:min(1.0,max(0.0,clean_base[k]+clean_overlay.get(k,0.0))) for k in DIMENSIONS}
    if clean_base != base_before: raise AssertionError("base mutated")
    diffs={k:effective[k]-clean_base[k] for k in DIMENSIONS}
    result={
        "schema_version":"1.0","policy_version":POLICY_VERSION,"experiment_id":experiment_id,
        "base_fingerprint":fingerprint(clean_base),"overlay_fingerprint":fingerprint(clean_overlay),
        "effective_fingerprint":fingerprint(effective),"base":clean_base,"overlay":clean_overlay,"effective":effective,
        "drift_mean_abs":sum(abs(v) for v in diffs.values())/len(DIMENSIONS),
        "drift_max_abs":max(abs(v) for v in diffs.values()),
        "rollback":{"restore_base_fingerprint":fingerprint(clean_base),"discard_overlay_fingerprint":fingerprint(clean_overlay)},
        "canonical_base_mutated":False,"promotion_status":"CANDIDATE_ONLY","test_required_bound":max_abs_delta
    }
    result["record_fingerprint"]=fingerprint(result)
    return result
