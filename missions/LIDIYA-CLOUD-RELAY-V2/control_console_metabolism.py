"""Fail-closed compaction for LCR-created control-plane metadata only."""
from __future__ import annotations
import hashlib, json
PROTECTED=("evidence/","state/","rollback","stable","identity","personality","governance","chat","credential","secret","token","key")
ALLOWED_KINDS={"progress_event","transient_envelope","reproducible_scratch"}

def _secret_like(path):
    p=path.lower(); return any(x in p for x in ("secret","credential","token",".env","private_key","apikey","api_key"))
def classify(item):
    path=str(item.get("path","")); low=path.lower()
    if _secret_like(path): return "QUARANTINE"
    if any(x in low for x in PROTECTED): return "KEEP"
    if item.get("kind") not in ALLOWED_KINDS: return "QUARANTINE"
    if not item.get("reproducible",False): return "QUARANTINE"
    return "WASTE" if item.get("duplicate",False) or item.get("expired",False) else "KEEP"

def compact(items):
    # Never retain content/value fields. Stable metadata-only summary.
    rows=[]
    for x in items:
        row={"id":str(x.get("id","")),"path":str(x.get("path","")),"kind":str(x.get("kind","")),"disposition":classify(x)}
        row["fingerprint"]=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        rows.append(row)
    unique={r["fingerprint"]:r for r in rows}
    ordered=sorted(unique.values(),key=lambda r:(r["disposition"],r["path"],r["id"]))
    return {"summary":ordered,"counts":{k:sum(r["disposition"]==k for r in ordered) for k in ("KEEP","QUARANTINE","WASTE")},"raw_content_retained":False}
