#!/usr/bin/env python3
"""Independent manifest verifier for a materialized frozen commit tree."""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path, PurePosixPath

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def safe_rel(value: str) -> bool:
    p=PurePosixPath(value)
    return not p.is_absolute() and ".." not in p.parts and value not in ("", ".")

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--manifest",type=Path,required=True)
    ap.add_argument("--allow-self-absent",action="store_true")
    ap.add_argument("--output",type=Path)
    a=ap.parse_args()
    manifest=json.loads(a.manifest.read_text(encoding="utf-8"))
    entries=manifest.get("files",[])
    paths=[e.get("path") for e in entries]
    duplicates=sorted({p for p in paths if paths.count(p)>1})
    invalid_paths=sorted([p for p in paths if not isinstance(p,str) or not safe_rel(p)])
    listed=set(p for p in paths if isinstance(p,str) and safe_rel(p))
    actual=set(str(p.relative_to(a.root)).replace(os.sep,"/") for p in a.root.rglob("*") if p.is_file())
    manifest_rel=str(a.manifest.resolve().relative_to(a.root.resolve())).replace(os.sep,"/")
    missing=[]; mismatches=[]
    for e in entries:
        rel=e.get("path")
        if not isinstance(rel,str) or not safe_rel(rel): continue
        p=a.root/rel
        if not p.is_file():
            missing.append(rel); continue
        size=p.stat().st_size; sha=digest(p)
        if size!=e.get("size_bytes") or sha!=e.get("sha256"):
            mismatches.append({"path":rel,"expected_size":e.get("size_bytes"),"actual_size":size,"expected_sha256":e.get("sha256"),"actual_sha256":sha})
    extras=sorted(actual-listed-{manifest_rel})
    self_present=manifest_rel in listed
    self_rule_ok=self_present or a.allow_self_absent
    report={"status":"PASS","missing":sorted(missing),"extras":extras,"duplicates":duplicates,"invalid_paths":invalid_paths,"mismatches":mismatches,"manifest_self_entry":"PRESENT" if self_present else "ABSENT","self_rule_ok":self_rule_ok,"entry_count":len(entries)}
    if missing or extras or duplicates or invalid_paths or mismatches or not self_rule_ok:
        report["status"]="FAIL"
    text=json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(text+"\n",encoding="utf-8")
    print(text)
    return 0 if report["status"]=="PASS" else 1
if __name__=="__main__": raise SystemExit(main())
