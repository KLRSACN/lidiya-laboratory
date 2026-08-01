from __future__ import annotations
import json, os, tempfile, uuid
from pathlib import Path
from datetime import timedelta
from relay_common_v0_3 import *
class StorageMixin:
    STATE_VERSION='LOCAL_RELAY_DISPATCHER_STATE_V0.3'
    CHECKPOINT_VERSION='LOCAL_RELAY_CHECKPOINT_V0.3'
    def __init__(self,runtime_root,authorized_runtime_roots,dispatcher_id='LOCAL-RELAY-DISPATCHER-01',generation=1):
        if not authorized_runtime_roots: raise Unsafe('empty runtime root allowlist')
        self.root=Path(runtime_root).resolve(); self.allowlist=[Path(x).resolve() for x in authorized_runtime_roots]
        if not any(self.root==a or self.root.is_relative_to(a) for a in self.allowlist): raise Unsafe('runtime root not authorized')
        for a in self.allowlist:
            if not a.is_absolute(): raise Unsafe('allowlist must be absolute')
        self.dispatcher_id=dispatcher_id; self.generation=generation
        self.root.mkdir(parents=True,exist_ok=True)
        for d in ('inbox','running','outbox','failed','checkpoints','quarantine','state','state/journal','state/tasks'): self.safe_path(d).mkdir(parents=True,exist_ok=True)
        self.state_path=self.safe_path('state','dispatcher_state.json')
        if not self.state_path.exists(): self._write_state(self._default_state())
        else: self._validate_state(self.read_json(self.state_path))
        self.reconcile()
    def _default_state(self):
        return {'schema_version':self.STATE_VERSION,'dispatcher_id':self.dispatcher_id,'generation':self.generation,'runtime_root_allowlist_digest':sha256_bytes(canonical([str(x) for x in self.allowlist])),'last_reconciliation_at':None,'highest_progress_token':None,'counters':{s:0 for s in STATES},'completed_assignments':{},'task_index':{},'updated_at':iso(utc_now())}
    def _validate_state(self,s):
        need={'schema_version','dispatcher_id','generation','runtime_root_allowlist_digest','last_reconciliation_at','highest_progress_token','counters','completed_assignments','task_index','updated_at'}
        if need-set(s): raise Invalid('dispatcher state schema')
        if s['schema_version']!=self.STATE_VERSION: raise Invalid('dispatcher state version')
    def safe_path(self,*parts):
        p=self.root.joinpath(*parts).resolve()
        try:p.relative_to(self.root)
        except ValueError as e: raise Unsafe('path escape') from e
        return p
    def _inside(self,p):
        p=Path(p).resolve()
        try:p.relative_to(self.root)
        except ValueError as e: raise Unsafe('path escape') from e
        return p
    def atomic_write(self,p,b):
        p=self._inside(p);p.parent.mkdir(parents=True,exist_ok=True);fd,t=tempfile.mkstemp(prefix='.'+p.name+'.',suffix='.tmp',dir=p.parent)
        try:
            with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
            os.replace(t,p)
        finally:
            if os.path.exists(t):os.unlink(t)
    def write_json(self,p,v): self.atomic_write(p,(json.dumps(v,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode())
    def read_json(self,p):
        with self._inside(p).open(encoding='utf-8') as f:v=json.load(f)
        if not isinstance(v,dict): raise Invalid('root not object')
        return v
    def _write_state(self,s): s['updated_at']=iso(utc_now());self.write_json(self.state_path,s)
    def state(self): return self.read_json(self.state_path)
    def task_path(self,task_id): return self.safe_path('state','tasks',f'{task_id}.json')
    def checkpoint_file(self,task_id): return self.safe_path('checkpoints',f'{task_id}.checkpoint.json')
    def outbox_path(self,p): return self.safe_path('outbox',slug(p)+'.result.json')
    def journal_path(self,p): return self.safe_path('state','journal',slug(p)+'.journal.json')
    def validate_packet(self,p):
        if not isinstance(p,dict): raise Invalid('packet object')
        unknown=set(p)-ALLOWED_FIELDS
        if unknown: raise Invalid('unknown fields:'+','.join(sorted(unknown)))
        miss=REQ-set(p)
        if miss: raise Invalid('missing:'+','.join(sorted(miss)))
        for k in ('schema_version','mission_id','token','task_id','target_worker','action','objective','created_at'):
            if not isinstance(p[k],str) or not p[k].strip(): raise Invalid('empty:'+k)
        if p['schema_version']!='LOCAL_RELAY_TASK_V0.3': raise Invalid('schema_version')
        parse_iso(p['created_at'])
        if p['action'] not in ACTIONS: raise Invalid('unsupported action')
        if p['target_worker']!='ANY' and not (p['target_worker'].startswith('W') and p['target_worker'][1:].isdigit()): raise Invalid('target_worker')
        if not isinstance(p['payload'],dict): raise Invalid('payload')
        for k in ('success_criteria','evidence_required'):
            if not isinstance(p[k],list) or not p[k] or any(not isinstance(x,str) or not x.strip() for x in p[k]): raise Invalid(k)
        if not isinstance(p['attempt'],int) or p['attempt']<0: raise Invalid('attempt')
        if not isinstance(p['max_attempts'],int) or p['max_attempts']<1 or p['attempt']>p['max_attempts']: raise Invalid('max_attempts')
        if not isinstance(p['lease_seconds'],int) or not 5<=p['lease_seconds']<=3600: raise Invalid('lease_seconds')
        for k in ('lease_generation','recovery_count'):
            if not isinstance(p.get(k,0),int) or p.get(k,0)<0: raise Invalid(k)
        if p.get('packet_sha256') and p['packet_sha256']!=packet_hash(p): raise Invalid('hash')
    def _task_record(self,p,state,**kw):
        if state not in STATES: raise Invalid('state')
        old=self.read_task_state(p['task_id'])
        if old and old.get('token')==p.get('token') and old['state']=='completed' and state in {'pending','running'}: raise Invalid('completed regression')
        if old and old['state']=='cancelled' and state not in {'cancelled'}: raise Invalid('cancelled execution')
        rec={'schema_version':'LOCAL_RELAY_TASK_STATE_V0.3','mission_id':p['mission_id'],'token':p['token'],'task_id':p['task_id'],'generation':self.generation,'state':state,'action':p['action'],'attempt':p['attempt'],'lease_generation':p.get('lease_generation',0),'recovery_count':p.get('recovery_count',0),'highest_progress_token':kw.pop('highest_progress_token',old.get('highest_progress_token') if old else progress_token(p,0)),'updated_at':iso(utc_now()),**kw}
        self.write_json(self.task_path(p['task_id']),rec)
        s=self.state();s['task_index'][p['task_id']]=state;s['counters']={x:sum(1 for v in s['task_index'].values() if v==x) for x in STATES};s['highest_progress_token']=rec['highest_progress_token'];self._write_state(s)
        return rec
    def read_task_state(self,task_id):
        p=self.task_path(task_id);return self.read_json(p) if p.exists() else None
    def _checkpoint(self,p,state,worker_id=None,claim_id=None,result_hash=None,step=0):
        old=self.read_checkpoint(p['task_id']); token=progress_token(p,step)
        if old and token<old['highest_progress_token']: token=old['highest_progress_token']
        cp={'schema_version':self.CHECKPOINT_VERSION,'mission_id':p['mission_id'],'task_id':p['task_id'],'token':p['token'],'generation':self.generation,'state':state,'worker_id':worker_id,'claim_id':claim_id,'lease_generation':p.get('lease_generation',0),'recovery_count':p.get('recovery_count',0),'highest_progress_token':token,'updated_at':iso(utc_now()),'result_hash':result_hash,'runtime_root_authorization':{'root':str(self.root),'allowlist_digest':self.state()['runtime_root_allowlist_digest'],'authorized':True}}
        self.write_json(self.checkpoint_file(p['task_id']),cp);return cp
    def read_checkpoint(self,task_id):
        p=self.checkpoint_file(task_id);return self.read_json(p) if p.exists() else None
    def enqueue(self,p,name=None):
        p=dict(p);p.setdefault('lease_generation',0);p.setdefault('recovery_count',0);self.validate_packet(p)
        old=self.read_task_state(p['task_id'])
        if old and old.get('token')==p.get('token') and old['state'] in {'cancelled','completed'}: return None
        n=name or slug(p)+'.json'
        if Path(n).name!=n: raise Unsafe('filename')
        dest=self.safe_path('inbox',n);self.write_json(dest,p);self._task_record(p,'pending',highest_progress_token=progress_token(p,0));self._checkpoint(p,'pending',step=0);return dest
    def cancel_task(self,task_id):
        r=self.read_task_state(task_id)
        if not r: raise Invalid('unknown task')
        if r['state']=='completed': raise Invalid('completed cannot cancel')
        p={'mission_id':r['mission_id'],'token':r['token'],'task_id':task_id,'action':r['action'],'attempt':r['attempt'],'lease_generation':r['lease_generation'],'recovery_count':r['recovery_count']}
        return self._task_record(p,'cancelled',highest_progress_token=r['highest_progress_token'])
    def claim_next(self,worker_id,now=None):
        current=now or utc_now()
        for src in sorted(self.safe_path('inbox').glob('*.json')):
            cid=uuid.uuid4().hex;run=self.safe_path('running',src.stem+f'.__owner__{worker_id}.__claim__{cid}.json')
            try:os.replace(src,run)
            except OSError:continue
            try:
                p=self.read_json(run);self.validate_packet(p)
                tr=self.read_task_state(p['task_id'])
                if tr and tr['state']=='cancelled':run.unlink();continue
                if p['target_worker'] not in (worker_id,'ANY'):os.replace(run,src);continue
                if self.completed_record(p) or self.outbox_path(p).exists():run.unlink();return None
                p['lease_generation']=p.get('lease_generation',0)+1
                p['lease']={'worker_id':worker_id,'claim_id':cid,'lease_generation':p['lease_generation'],'claimed_at':iso(current),'heartbeat_at':iso(current),'lease_expires_at':iso(current+timedelta(seconds=p['lease_seconds']))}
                self.write_json(run,p);self._task_record(p,'running',worker_id=worker_id,claim_id=cid,highest_progress_token=progress_token(p,1));self._checkpoint(p,'running',worker_id,cid,step=1)
                return Claim(run,p,worker_id,cid,p['lease_generation'])
            except Exception as e:self.quarantine(run,str(e))
        return None
    def _live(self,claim,worker_id,lease_generation=None,now=None):
        current=now or utc_now();path=claim.path if isinstance(claim,Claim) else Path(claim);path=self._inside(path)
        if not path.exists():raise Invalid('stale claim')
        p=self.read_json(path);self.validate_packet(p);l=p.get('lease') or {}
        expected=claim.claim_id if isinstance(claim,Claim) else None;gen=lease_generation if lease_generation is not None else (claim.lease_generation if isinstance(claim,Claim) else None)
        if l.get('worker_id')!=worker_id:raise Invalid('worker')
        if expected and l.get('claim_id')!=expected:raise Invalid('claim_id')
        if gen is not None and l.get('lease_generation')!=gen:raise Invalid('lease_generation')
        if l.get('lease_generation')!=p.get('lease_generation'):raise Invalid('generation mismatch')
        if parse_iso(l['lease_expires_at'])<=current:raise Invalid('lease expired')
        return path,p
    def heartbeat(self,claim,worker_id,lease_generation=None,now=None):
        current=now or utc_now();path,p=self._live(claim,worker_id,lease_generation,current);p['lease']['heartbeat_at']=iso(current);p['lease']['lease_expires_at']=iso(current+timedelta(seconds=p['lease_seconds']));self.write_json(path,p);self._checkpoint(p,'running',worker_id,p['lease']['claim_id'],step=2);return p
    def quarantine(self,path,reason):
        path=self._inside(path);q=self.safe_path('quarantine',path.name)
        if q.exists():q=self.safe_path('quarantine',path.stem+'.'+uuid.uuid4().hex+'.json')
        os.replace(path,q);self.write_json(self.safe_path('quarantine',q.name+'.reason.json'),{'reason':reason});return q
    def completed_record(self,p_or_task):
        key=p_or_task if isinstance(p_or_task,str) and '::' in p_or_task else assignment_key(p_or_task)
        return self.state()['completed_assignments'].get(key)
    def read_completed_record(self,task_id):
        r=self.read_task_state(task_id)
        if not r:return None
        return self.completed_record(f"{r['mission_id']}::{r['token']}::{task_id}")
