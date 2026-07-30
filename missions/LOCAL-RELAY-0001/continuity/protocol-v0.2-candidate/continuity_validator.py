#!/usr/bin/env python3
"""Read-only static validator for a materialized Builder frozen commit directory."""
from __future__ import annotations
import argparse, ast, hashlib, json
from pathlib import Path

REQUIRED_TASK={"mission_id","token","task_id","target_worker","action","objective","created_at","attempt","max_attempts","lease_seconds","payload","success_criteria","evidence_required"}
REQUIRED_CHECKPOINT={"current_state","highest_progress_token","next_action","completed_steps","pending_steps","result_hash","recoverable"}
REQUIRED_COMPLETED={"status","result_hash","completed_at","worker_id","attempt","outbox_path"}

def sha256(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def inspect_source(text:str)->dict:
 ast.parse(text)
 return {
  "attempt_max_invariant":"attempt" in text and "max_attempts" in text,
  "lease_bounds":"lease_seconds" in text and "3600" in text and "5" in text,
  "claim_id":"claim_id" in text,
  "lease_generation":"lease_generation" in text,
  "recovery_count":"recovery_count" in text,
  "outbox_path":"outbox_path" in text,
  "stale_claim_guard":all(x in text for x in ("claim_id","lease_generation","lease_expires_at")),
  "path_containment":"relative_to" in text and "resolve" in text,
  "registry_reconciliation":("reconcile" in text or "journal" in text) and "completed" in text and "outbox" in text,
 }

def validate(root:Path)->dict:
 report={"root":str(root),"errors":[],"checks":{}}
 manifest_path=root/"manifest.json"
 if not manifest_path.exists():
  report["errors"].append("manifest missing");report["status"]="FAIL";return report
 manifest=json.loads(manifest_path.read_text("utf-8"))
 entries=manifest.get("files",[]);report["checks"]["manifest_file_count"]=len(entries)
 for entry in entries:
  path=root/entry["path"]
  if not path.exists():report["errors"].append("missing:"+entry["path"]);continue
  if path.stat().st_size!=entry["size_bytes"]:report["errors"].append("size:"+entry["path"])
  if sha256(path)!=entry["sha256"]:report["errors"].append("sha256:"+entry["path"])
 report["checks"]["sources"]={p.name:inspect_source(p.read_text("utf-8")) for p in root.glob("*.py")}
 for path in root.glob("*.json"):
  try:json.loads(path.read_text("utf-8"))
  except Exception as exc:report["errors"].append(f"json:{path.name}:{exc}")
 report["status"]="PASS" if not report["errors"] else "FAIL"
 return report

def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("materialized_builder_directory",type=Path);parser.add_argument("--output",type=Path)
 args=parser.parse_args();report=validate(args.materialized_builder_directory.resolve());data=json.dumps(report,indent=2,sort_keys=True)+"\n"
 if args.output:args.output.write_text(data,"utf-8")
 else:print(data,end="")
 return 0 if report["status"]=="PASS" else 1

if __name__=="__main__":raise SystemExit(main())
