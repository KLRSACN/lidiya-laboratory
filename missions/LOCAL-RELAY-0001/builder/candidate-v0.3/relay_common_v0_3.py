from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REQ = {'mission_id','token','task_id','target_worker','action','objective','created_at','attempt','max_attempts','lease_seconds','payload','success_criteria','evidence_required'}
DIRS = ('inbox','running','outbox','failed','checkpoints','quarantine','state')
SUPPORTED_ACTIONS = {'WRITE_TEXT'}
NONEMPTY_FIELDS = ('mission_id','token','task_id','target_worker','action','objective','created_at')
class Invalid(Exception): pass
class Unsafe(Exception): pass
class FaultInjected(Exception): pass
UnsafePath = Unsafe

@dataclass
class Claim:
    path: Path
    packet: dict
    worker_id: str
    claim_id: str
    lease_generation: int

def utc_now(): return datetime.now(timezone.utc)
def iso(value): return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
def parse_dt(value):
    if not isinstance(value, str) or not value.strip(): raise Invalid('created_at/lease timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:
        raise Invalid('invalid ISO 8601') from exc
    if parsed.tzinfo is None: raise Invalid('timezone required')
    return parsed.astimezone(timezone.utc)
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode()
def sha256_bytes(value): return hashlib.sha256(value).hexdigest()
def packet_hash(packet):
    value = dict(packet)
    for field in ('packet_sha256','lease','failure_reason','recovery_count','lease_generation'):
        value.pop(field, None)
    value.pop('attempt', None)
    return sha256_bytes(canonical(value))
def assignment_key(packet): return f"{packet['mission_id']}::{packet['token']}::{packet['task_id']}"
def assignment_slug(packet): return f"{packet['mission_id']}__{packet['token']}__{packet['task_id']}"
