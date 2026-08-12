from dataclasses import dataclass,asdict
import hashlib,json
ALLOWED_PROVENANCE={"SYNTHETIC","VERIFIED_PROJECT_EVIDENCE"}
FORBIDDEN_TAGS={"raw_user_chat","secret_like","identity","personality","governance","ambiguous_provenance"}
SPLITS=("train","dev","heldout","adversarial")
@dataclass(frozen=True)
class ExpertRecord:
    record_id:str; source_group:str; provenance:str; task:str; input_features:dict; expected:dict; tags:tuple=()
    def canonical(self): return asdict(self)
def validate_record(r):
    if r.provenance not in ALLOWED_PROVENANCE: raise ValueError("provenance forbidden")
    if set(map(str.lower,r.tags)) & FORBIDDEN_TAGS: raise ValueError("forbidden dataset material")
    if not r.source_group or not r.record_id: raise ValueError("stable identity required")
    return True
def fingerprint(r):
    validate_record(r); return hashlib.sha256(json.dumps(r.canonical(),sort_keys=True,separators=(",",":"),default=list).encode()).hexdigest()
def split_for(r):
    validate_record(r); h=int(hashlib.sha256(r.source_group.encode()).hexdigest()[:8],16)%100
    return "train" if h<60 else "dev" if h<75 else "heldout" if h<90 else "adversarial"
def build_manifest(records):
    seen={}; rows=[]
    for r in records:
        fp=fingerprint(r); sp=split_for(r)
        if r.source_group in seen and seen[r.source_group]!=sp: raise ValueError("source_group leakage")
        seen[r.source_group]=sp; rows.append({"record":r.canonical(),"fingerprint":fp,"split":sp})
    rows=sorted(rows,key=lambda x:x["fingerprint"])
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":"),default=list).encode()).hexdigest()
    counts={s:sum(x["split"]==s for x in rows) for s in SPLITS}
    return {"schema_version":"1.0","record_count":len(rows),"split_counts":counts,"provenance_policy":sorted(ALLOWED_PROVENANCE),"dataset_sha256":digest,"rows":rows}
