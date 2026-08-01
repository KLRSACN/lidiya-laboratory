from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
REQ={'schema_version','mission_id','token','task_id','target_worker','action','objective','created_at','attempt','max_attempts','lease_seconds','payload','success_criteria','evidence_required'}
ALLOWED_FIELDS=REQ|{'packet_sha256','lease_generation','recovery_count','lease'}
ACTIONS={'WRITE_TEXT'}
STATES={'pending','running','completed','failed','blocked','cancelled'}
class Invalid(Exception): pass
class Unsafe(Exception): pass
class FaultInjected(Exception): pass
UnsafePath=Unsafe
@dataclass(frozen=True)
class Claim:
    path: Path; packet: dict; worker_id: str; claim_id: str; lease_generation: int

def utc_now(): return datetime.now(timezone.utc)
def iso(v): return v.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
def parse_iso(v):
    if not isinstance(v,str) or not v.strip(): raise Invalid('timestamp')
    try: d=datetime.fromisoformat(v.replace('Z','+00:00'))
    except ValueError as e: raise Invalid('timestamp') from e
    if d.tzinfo is None: raise Invalid('timestamp timezone')
    return d.astimezone(timezone.utc)
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha256_bytes(v): return hashlib.sha256(v).hexdigest()
def assignment_key(p): return f"{p['mission_id']}::{p['token']}::{p['task_id']}"
def slug(p): return f"{p['mission_id']}__{p['token']}__{p['task_id']}"
def packet_hash(p):
    q={k:v for k,v in p.items() if k not in {'packet_sha256','lease_generation','recovery_count','lease','failure_reason','attempt'}}
    return sha256_bytes(canonical(q))
def progress_token(p,step): return f"{p['mission_id']}:{p['token']}:{p['task_id']}:P{step:04d}"
