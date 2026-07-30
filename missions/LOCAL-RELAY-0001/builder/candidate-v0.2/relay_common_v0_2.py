from __future__ import annotations
import hashlib,json,os,tempfile,uuid
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Any
REQ={"mission_id","token","task_id","target_worker","action","objective","created_at","attempt","max_attempts","lease_seconds","payload","success_criteria","evidence_required"}
DIRS=("inbox","running","outbox","failed","checkpoints","quarantine","state","state/journal","state/outputs")
def utc_now(): return datetime.now(timezone.utc)
def iso(v): return v.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
def parse_dt(v): return datetime.fromisoformat(v.replace("Z","+00:00"))
def canonical(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
def sha256_bytes(v): return hashlib.sha256(v).hexdigest()
def packet_hash(p): return sha256_bytes(canonical({k:p[k] for k in REQ-{"attempt"} if k in p}))
def assignment_key(p): return f"{p['mission_id']}::{p['token']}::{p['task_id']}"
def assignment_slug(p): return f"{p['mission_id']}__{p['token']}__{p['task_id']}"
class Invalid(Exception): pass
class Unsafe(Exception): pass
UnsafePath=Unsafe
@dataclass(frozen=True)
class Claim:
 path:Path
 packet:dict[str,Any]
 worker_id:str
 claim_id:str
class FaultInjected(RuntimeError): pass
