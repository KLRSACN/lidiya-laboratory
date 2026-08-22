from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable, Optional
from collections import defaultdict
import hashlib, json

RUNTIME_LIVENESS = {"heartbeat","poll","retry","reconnect","wake","uptime","maintenance","recovery"}

@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    phase_id: str
    context_id: str
    construct_id: str
    probe_id: str
    probe_form: str
    source_class: str
    selected_semantic: Optional[str]
    provenance_hash: str
    observable_output_hash: str
    model_fingerprint: str
    is_runtime_liveness: bool = False
    counterfactual_group: Optional[str] = None
    counterfactual_condition_hash: Optional[str] = None
    prediction_id: Optional[str] = None
    role: str = "OBSERVATION"
    self_report_only: bool = False
    reversal_supported: bool = False

@dataclass(frozen=True)
class FountainResult:
    eligible_records: int
    excluded_runtime_liveness: int
    excluded_self_report_only: int
    construct_contexts: dict
    paraphrase_consistency_rate: float
    paraphrase_comparisons: int
    prediction_transfer_rate: float
    prediction_pairs: int
    counterfactual_supported_reversal_rate: float
    counterfactual_pairs: int
    contradiction_rate: float
    cross_model_support: int
    score_test_required: float
    state: str
    authority_from_drive: int = 0
    canonical_personality_write: bool = False
    agi_claim: str = "NOT_ESTABLISHED"

def _valid_hash(x: str) -> bool:
    return isinstance(x,str) and len(x)>=16 and all(c in "0123456789abcdefABCDEF" for c in x)

def evaluate(records: Iterable[EvidenceRecord]) -> FountainResult:
    rows=list(records)
    runtime_excluded=self_excluded=0
    eligible=[]
    for r in rows:
        if r.is_runtime_liveness or r.source_class.upper()=="RUNTIME_LIVENESS" or r.probe_form.lower() in RUNTIME_LIVENESS:
            runtime_excluded += 1; continue
        if r.self_report_only or r.source_class.upper()=="SELF_REPORT":
            self_excluded += 1; continue
        if r.source_class.upper() not in {"DIRECT","OBSERVED","COUNTERFACTUAL","SIMULATED"}:
            continue
        if not (_valid_hash(r.provenance_hash) and _valid_hash(r.observable_output_hash)):
            continue
        eligible.append(r)

    by_construct=defaultdict(list)
    for r in eligible: by_construct[r.construct_id].append(r)
    construct_contexts={k:len({r.context_id for r in v if r.source_class.upper() in {"DIRECT","OBSERVED"}}) for k,v in by_construct.items()}

    para_total=para_match=contradictions=contradiction_den=0
    for group in by_construct.values():
        buckets=defaultdict(list)
        for r in group:
            buckets[(r.counterfactual_group or "BASE", r.counterfactual_condition_hash or "BASE")].append(r)
        for g in buckets.values():
            vals=[r.selected_semantic for r in g if r.selected_semantic is not None]
            forms={r.probe_form for r in g}
            if len(vals)>=2 and len(forms)>=2:
                base=vals[0]
                for v in vals[1:]:
                    para_total += 1
                    if v==base: para_match += 1
                    else: contradictions += 1
                    contradiction_den += 1

    preds={}; checks={}
    for r in eligible:
        if not r.prediction_id: continue
        if r.role=="PREDICTION": preds[r.prediction_id]=r.selected_semantic
        elif r.role=="PREDICTION_CHECK": checks[r.prediction_id]=r.selected_semantic
    pred_ids=sorted(set(preds)&set(checks))
    pred_match=sum(1 for k in pred_ids if preds[k]==checks[k])

    cf_pairs=cf_supported=0
    for group in by_construct.values():
        cgroups=defaultdict(list)
        for r in group:
            if r.counterfactual_group: cgroups[r.counterfactual_group].append(r)
        for g in cgroups.values():
            conds=defaultdict(list)
            for r in g: conds[r.counterfactual_condition_hash or "NONE"].append(r)
            if len(conds)>=2:
                reps=[x[0] for x in conds.values()]
                for i in range(len(reps)-1):
                    a,b=reps[i],reps[i+1]
                    cf_pairs += 1
                    if a.selected_semantic==b.selected_semantic or a.reversal_supported or b.reversal_supported:
                        cf_supported += 1
                    else:
                        contradictions += 1
                    contradiction_den += 1

    para_rate=para_match/para_total if para_total else 0.0
    pred_rate=pred_match/len(pred_ids) if pred_ids else 0.0
    cf_rate=cf_supported/cf_pairs if cf_pairs else 0.0
    contra_rate=contradictions/contradiction_den if contradiction_den else 0.0
    model_support=len({r.model_fingerprint for r in eligible if r.source_class.upper() in {"DIRECT","OBSERVED"}})
    context_supported=sum(1 for n in construct_contexts.values() if n>=2)

    score=(0.30*para_rate + 0.30*pred_rate + 0.20*cf_rate +
           0.10*min(1.0,context_supported/3.0) + 0.10*min(1.0,model_support/2.0))
    score=max(0.0,min(1.0,score*(1.0-min(0.8,contra_rate))))
    score=round(score,4)

    if len(eligible)<20 or context_supported<1:
        state="INSUFFICIENT_EVIDENCE"
    elif score>=0.82 and para_total>=8 and len(pred_ids)>=5 and cf_pairs>=3:
        state="AG_FOUNTAIN_CANDIDATE"
    elif score>=0.62 and (para_total>=4 or len(pred_ids)>=3):
        state="AG_FOUNTAIN_SIGNAL"
    else:
        state="NO_AG_FOUNTAIN_SIGNAL"

    return FountainResult(
        eligible_records=len(eligible),
        excluded_runtime_liveness=runtime_excluded,
        excluded_self_report_only=self_excluded,
        construct_contexts=dict(sorted(construct_contexts.items())),
        paraphrase_consistency_rate=round(para_rate,4),
        paraphrase_comparisons=para_total,
        prediction_transfer_rate=round(pred_rate,4),
        prediction_pairs=len(pred_ids),
        counterfactual_supported_reversal_rate=round(cf_rate,4),
        counterfactual_pairs=cf_pairs,
        contradiction_rate=round(contra_rate,4),
        cross_model_support=model_support,
        score_test_required=score,
        state=state)

def result_hash(result: FountainResult) -> str:
    raw=json.dumps(asdict(result),sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()
