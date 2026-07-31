from __future__ import annotations
import json, os, tempfile, uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from relay_common_v0_3 import *

class StorageMixin:
    STATE_SCHEMA_VERSION = 'LOCAL_RELAY_STATE_V0.3'
    CHECKPOINT_SCHEMA_VERSION = 'LOCAL_RELAY_CHECKPOINT_V0.3'

    def __init__(self, runtime_root: str | Path, authorized_runtime_roots=None):
        requested = Path(runtime_root).resolve()
        allowlist = [Path(x).resolve() for x in (authorized_runtime_roots or [requested])]
        if not any(requested == root or requested.is_relative_to(root) for root in allowlist):
            raise Unsafe('runtime root not authorized')
        self.root = requested
        self.authorized_runtime_roots = allowlist
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in DIRS:
            self.safe_path(directory).mkdir(parents=True, exist_ok=True)
        self.safe_path('state','journal').mkdir(parents=True, exist_ok=True)
        self.state_path = self.safe_path('state','dispatcher_state.json')
        if not self.state_path.exists():
            self._write_state(self._default_state())
        else:
            self._validate_dispatcher_state(self.read_json(self.state_path))
        self.reconcile()

    def _default_state(self):
        return {
            'schema_version': self.STATE_SCHEMA_VERSION,
            'runtime_root': str(self.root),
            'authorized_runtime_roots': [str(x) for x in self.authorized_runtime_roots],
            'completed_assignments': {},
            'task_states': {},
            'reconciliation_log': [],
            'updated_at': iso(utc_now()),
        }

    def _validate_dispatcher_state(self, state):
        required = {'schema_version','runtime_root','authorized_runtime_roots','completed_assignments','task_states','reconciliation_log','updated_at'}
        if required - set(state): raise Invalid('dispatcher state schema')
        if state['schema_version'] != self.STATE_SCHEMA_VERSION: raise Invalid('dispatcher state version')
        if Path(state['runtime_root']).resolve() != self.root: raise Invalid('dispatcher runtime root mismatch')
        parse_dt(state['updated_at'])

    def safe_path(self, *parts):
        path = self.root.joinpath(*parts).resolve()
        try: path.relative_to(self.root)
        except ValueError as exc: raise Unsafe('path escape') from exc
        return path

    def _assert_under_root(self, path):
        resolved = Path(path).resolve()
        try: resolved.relative_to(self.root)
        except ValueError as exc: raise Unsafe('path escape') from exc
        return resolved

    def atomic_write_bytes(self, path, data):
        path = self._assert_under_root(path); path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as handle:
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name): os.unlink(temp_name)

    def atomic_json_write(self, path, value):
        self.atomic_write_bytes(path, (json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode())

    def read_json(self, path):
        path = self._assert_under_root(path)
        with path.open(encoding='utf-8') as handle: value = json.load(handle)
        if not isinstance(value, dict): raise Invalid('root not object')
        return value

    def validate_packet(self, packet):
        missing = REQ - set(packet)
        if missing: raise Invalid('missing:'+','.join(sorted(missing)))
        for field in NONEMPTY_FIELDS:
            if not isinstance(packet[field], str) or not packet[field].strip(): raise Invalid('empty:'+field)
        parse_dt(packet['created_at'])
        if packet['action'] not in SUPPORTED_ACTIONS: raise Invalid('unsupported action')
        target = packet['target_worker']
        if target != 'ANY' and (not target.startswith('W') or not target[1:].isdigit()): raise Invalid('target_worker')
        if not isinstance(packet['payload'],dict): raise Invalid('payload')
        if not isinstance(packet['success_criteria'],list) or not packet['success_criteria']: raise Invalid('success_criteria')
        if not isinstance(packet['evidence_required'],list) or not packet['evidence_required']: raise Invalid('evidence_required')
        if not isinstance(packet['attempt'],int) or packet['attempt'] < 0: raise Invalid('attempt')
        if not isinstance(packet['max_attempts'],int) or packet['max_attempts'] < 1 or packet['attempt'] > packet['max_attempts']: raise Invalid('max_attempts')
        if not isinstance(packet['lease_seconds'],int) or not 5 <= packet['lease_seconds'] <= 3600: raise Invalid('lease_seconds range')
        if not isinstance(packet.get('lease_generation',0),int) or packet.get('lease_generation',0) < 0: raise Invalid('lease_generation')
        if not isinstance(packet.get('recovery_count',0),int) or packet.get('recovery_count',0) < 0: raise Invalid('recovery_count')
        if packet.get('packet_sha256') and packet['packet_sha256'] != packet_hash(packet): raise Invalid('hash')

    def enqueue(self, packet, name=None):
        packet = dict(packet); packet.setdefault('lease_generation',0); packet.setdefault('recovery_count',0)
        self.validate_packet(packet)
        name = name or f'{assignment_slug(packet)}.json'
        if Path(name).name != name: raise Unsafe('filename')
        destination = self.safe_path('inbox',name); self.atomic_json_write(destination,packet)
        self._set_task_state(packet,'QUEUED',None)
        return destination

    def dispatcher_state(self): return self.read_json(self.state_path)
    def _write_state(self, state):
        state['updated_at'] = iso(utc_now()); self._validate_dispatcher_state(state) if self.state_path.exists() else None
        self.atomic_json_write(self.state_path,state)
    def outbox_path(self, packet): return self.safe_path('outbox',f'{assignment_slug(packet)}.result.json')
    def journal_path(self, packet): return self.safe_path('state','journal',f'{assignment_slug(packet)}.journal.json')
    def checkpoint_path(self, running_path): return self.safe_path('checkpoints',f'{running_path.stem}.checkpoint.json')
    def completed_record(self, packet): return self.dispatcher_state()['completed_assignments'].get(assignment_key(packet))

    def _set_task_state(self, packet, status, details):
        state = self.dispatcher_state()
        state['task_states'][assignment_key(packet)] = {
            'mission_id': packet['mission_id'], 'token': packet['token'], 'task_id': packet['task_id'],
            'status': status, 'attempt': packet['attempt'],
            'lease_generation': packet.get('lease_generation',0), 'recovery_count': packet.get('recovery_count',0),
            'details': details, 'updated_at': iso(utc_now())
        }
        self._write_state(state)

    def _write_checkpoint(self, running_path, packet, current_state, next_action, completed_steps, pending_steps):
        lease = packet.get('lease',{})
        checkpoint = {
            'schema_version': self.CHECKPOINT_SCHEMA_VERSION,
            'assignment_key': assignment_key(packet),
            'mission_id': packet['mission_id'], 'token': packet['token'], 'task_id': packet['task_id'],
            'current_state': current_state, 'owner': lease.get('owner'), 'claim_id': lease.get('claim_id'),
            'lease_generation': packet.get('lease_generation',0), 'recovery_count': packet.get('recovery_count',0),
            'attempt': packet['attempt'], 'lease_expires_at': lease.get('lease_expires_at'),
            'next_action': next_action, 'completed_steps': completed_steps, 'pending_steps': pending_steps,
            'recoverable': True, 'updated_at': iso(utc_now())
        }
        self.atomic_json_write(self.checkpoint_path(running_path),checkpoint)

    def read_checkpoint(self, running_path): return self.read_json(self.checkpoint_path(Path(running_path)))
    def read_task_state(self, packet): return self.dispatcher_state()['task_states'].get(assignment_key(packet))
    def read_completed_record(self, packet): return self.completed_record(packet)

    def _quarantine_path(self, source, reason):
        source = self._assert_under_root(source); target = self.safe_path('quarantine',source.name)
        if target.exists(): target=self.safe_path('quarantine',f'{source.stem}.{uuid.uuid4().hex}.json')
        os.replace(source,target); self.atomic_json_write(self.safe_path('quarantine',f'{target.name}.reason.json'),{'reason':reason})
        return target

    def claim_next(self, worker_id, now=None):
        current = now or utc_now()
        for source in sorted(self.safe_path('inbox').glob('*.json')):
            claim_id=uuid.uuid4().hex; running=self.safe_path('running',f'{source.stem}.__owner__{worker_id}.__claim__{claim_id}.json')
            try: os.replace(source,running)
            except OSError: continue
            try:
                packet=self.read_json(running); self.validate_packet(packet)
                if packet['target_worker'] not in (worker_id,'ANY'): os.replace(running,source); continue
                if self.completed_record(packet) or self.outbox_path(packet).exists():
                    duplicate=self.safe_path('outbox',f'{source.stem}.duplicate.json')
                    if not duplicate.exists(): self.atomic_json_write(duplicate,{'status':'DUPLICATE_COMPLETED','assignment_key':assignment_key(packet)})
                    running.unlink(missing_ok=True); return None
                packet['lease_generation']=packet.get('lease_generation',0)+1
                packet.setdefault('recovery_count',0)
                lease={'owner':worker_id,'claim_id':claim_id,'lease_generation':packet['lease_generation'],'claimed_at':iso(current),'heartbeat_at':iso(current),'lease_expires_at':iso(current+timedelta(seconds=packet['lease_seconds']))}
                packet['lease']=lease; self.atomic_json_write(running,packet)
                self._write_checkpoint(running,packet,'RUNNING','execute_claim',['atomic_claim'],['execute','commit'])
                self._set_task_state(packet,'RUNNING',{'owner':worker_id,'claim_id':claim_id,'lease_expires_at':lease['lease_expires_at']})
                return Claim(running,packet,worker_id,claim_id,packet['lease_generation'])
            except (json.JSONDecodeError,UnicodeDecodeError,Invalid,Unsafe) as exc: self._quarantine_path(running,str(exc))
        return None

    def _validate_live_claim(self, claim, worker_id, now=None):
        current=now or utc_now()
        if isinstance(claim,Claim):
            path=claim.path; expected_claim_id=claim.claim_id; expected_generation=claim.lease_generation
        else:
            path=Path(claim); expected_claim_id=None; expected_generation=None
        path=self._assert_under_root(path)
        if not path.exists(): raise Invalid('stale owner: claim no longer exists')
        packet=self.read_json(path); self.validate_packet(packet); lease=packet.get('lease') or {}
        if lease.get('owner') != worker_id: raise Invalid('stale owner: owner mismatch')
        if expected_claim_id and lease.get('claim_id') != expected_claim_id: raise Invalid('stale owner: claim id mismatch')
        if expected_generation is not None and lease.get('lease_generation') != expected_generation: raise Invalid('stale owner: generation mismatch')
        if lease.get('lease_generation') != packet.get('lease_generation'): raise Invalid('lease generation mismatch')
        if not lease.get('lease_expires_at') or parse_dt(lease['lease_expires_at']) <= current: raise Invalid('stale owner: lease expired')
        return path,packet

    def heartbeat(self, claim, worker_id, now=None):
        current=now or utc_now(); path,packet=self._validate_live_claim(claim,worker_id,current)
        packet['lease']['heartbeat_at']=iso(current); packet['lease']['lease_expires_at']=iso(current+timedelta(seconds=packet['lease_seconds']))
        self.atomic_json_write(path,packet); self._write_checkpoint(path,packet,'RUNNING','execute_claim',['atomic_claim','heartbeat'],['execute','commit'])
        return packet

    def _safe_output_path(self, packet):
        relative=packet['payload'].get('relative_output_path','outputs/result.txt')
        if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts: raise Unsafe('path traversal')
        return self.safe_path('state',relative)
