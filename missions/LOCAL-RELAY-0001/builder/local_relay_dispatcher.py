import hashlib,json,os,tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path

REQ={'mission_id','token','task_id','target_worker','action','objective','created_at','attempt','max_attempts','lease_seconds','payload','success_criteria','evidence_required'}
DIRS=('inbox','running','outbox','failed','checkpoints','quarantine','state')

def now(): return datetime.now(timezone.utc)
def iso(x): return x.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
def dt(x): return datetime.fromisoformat(x.replace('Z','+00:00'))
def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def packet_hash(p):
 q=dict(p);[q.pop(k,None) for k in ('packet_sha256','lease','failure_reason')];return sha(canon(q))
def key(p): return f"{p['mission_id']}::{p['token']}::{p['task_id']}"
class Invalid(Exception): pass
class Unsafe(Exception): pass
UnsafePath=Unsafe
from dataclasses import dataclass
@dataclass
class Claim:
 path: Path
 packet: dict

class Dispatcher:
 def __init__(self,root):
  self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
  for d in DIRS:(self.root/d).mkdir(exist_ok=True)
  self.sp=self.root/'state/dispatcher_state.json'
  if not self.sp.exists():self.write(self.sp,{'completed_assignments':{}})
 def safe_path(self,*p):
  x=self.root.joinpath(*p).resolve()
  try:x.relative_to(self.root)
  except ValueError:raise Unsafe('path escape')
  return x
 def path(self,*p):return self.safe_path(*p)
 def writeb(self,p,b):
  p=Path(p).resolve();p.relative_to(self.root);p.parent.mkdir(parents=True,exist_ok=True)
  fd,t=tempfile.mkstemp(prefix='.'+p.name+'.',suffix='.tmp',dir=p.parent)
  try:
   with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
   os.replace(t,p)
  finally:
   if os.path.exists(t):os.unlink(t)
 def write(self,p,x):self.writeb(p,(json.dumps(x,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode())
 def read(self,p):
  with open(p,encoding='utf-8') as f:x=json.load(f)
  if not isinstance(x,dict):raise Invalid('root not object')
  return x
 def valid(self,p):
  m=REQ-set(p)
  if m:raise Invalid('missing:'+','.join(sorted(m)))
  if p['action']!='WRITE_TEXT':raise Invalid('unsupported action')
  if not isinstance(p['payload'],dict):raise Invalid('payload')
  if not isinstance(p['attempt'],int) or p['attempt']<0:raise Invalid('attempt')
  if not isinstance(p['max_attempts'],int) or p['max_attempts']<1 or p['attempt']>p['max_attempts']:raise Invalid('max_attempts')
  if not isinstance(p['lease_seconds'],int) or p['lease_seconds']<1:raise Invalid('lease')
  if p.get('packet_sha256') and p['packet_sha256']!=packet_hash(p):raise Invalid('hash')
 def enqueue(self,p,name=None):
  self.valid(p);name=name or f"{p['mission_id']}__{p['token']}__{p['task_id']}.json"
  if Path(name).name!=name:raise Unsafe('filename')
  x=self.safe_path('inbox',name);self.write(x,p);return x
 def quarantine(self,p,why):
  q=self.safe_path('quarantine',p.name);os.replace(p,q);self.write(self.safe_path('quarantine',p.name+'.reason.json'),{'reason':why});return q
 def state(self):return self.read(self.sp)
 def out(self,p):return self.safe_path('outbox',f"{p['mission_id']}__{p['token']}__{p['task_id']}.result.json")
 def done(self,p):return self.state()['completed_assignments'].get(key(p))
 def claim(self,w,t=None):
  t=t or now()
  for s in sorted((self.root/'inbox').glob('*.json')):
   r=self.safe_path('running',s.stem+'.__owner__'+w+'.json')
   try:os.replace(s,r)
   except OSError:continue
   try:
    p=self.read(r);self.valid(p)
    if p['target_worker'] not in (w,'ANY'):os.replace(r,s);continue
    if self.done(p) or self.out(p).exists():
     d=self.safe_path('outbox',s.stem+'.duplicate.json')
     if not d.exists():self.write(d,{'status':'DUPLICATE_COMPLETED','assignment_key':key(p)})
     r.unlink();return None
    p['lease']={'owner':w,'claimed_at':iso(t),'heartbeat_at':iso(t),'lease_expires_at':iso(t+timedelta(seconds=p['lease_seconds']))};self.write(r,p)
    self.write(self.safe_path('checkpoints',r.stem+'.checkpoint.json'),{'assignment_key':key(p),'owner':w,'current_state':'RUNNING','attempt':p['attempt'],'lease_expires_at':p['lease']['lease_expires_at']})
    return Claim(r,p)
   except (json.JSONDecodeError,UnicodeDecodeError,Invalid) as e:self.quarantine(r,str(e))
  return None
 def heartbeat(self,r,w,t=None):
  t=t or now();r=Path(r).resolve();r.relative_to(self.safe_path('running'));p=self.read(r)
  if p.get('lease',{}).get('owner')!=w:raise Invalid('owner')
  p['lease']['heartbeat_at']=iso(t);p['lease']['lease_expires_at']=iso(t+timedelta(seconds=p['lease_seconds']));self.write(r,p);return p
 def fail(self,r,p,why,terminal=False):
  a=p['attempt']+1;p.pop('lease',None);p['attempt']=a;p['failure_reason']=why
  if terminal or a>=p['max_attempts']:
   f=self.safe_path('failed',r.name);self.write(f,p);r.unlink();return {'status':'FAILED','attempt':a}
  i=self.safe_path('inbox',r.name.split('.__owner__')[0]+'.json');p.pop('failure_reason',None);self.write(i,p);r.unlink();return {'status':'RETRY_SCHEDULED','attempt':a}
 def execute(self,r,w):
  if isinstance(r,Claim):r=r.path
  p=self.read(r)
  if p.get('lease',{}).get('owner')!=w:raise Invalid('owner')
  if self.done(p) or self.out(p).exists():r.unlink();return {'status':'DUPLICATE_COMPLETED'}
  rel=p['payload'].get('relative_output_path','outputs/result.txt')
  if not isinstance(rel,str) or Path(rel).is_absolute() or '..' in Path(rel).parts:return self.fail(r,p,'path traversal',True)
  text=p['payload'].get('text')
  if not isinstance(text,str):return self.fail(r,p,'text')
  o=self.safe_path('state',rel);self.writeb(o,text.encode());res={'status':'COMPLETED','mission_id':p['mission_id'],'token':p['token'],'task_id':p['task_id'],'worker_id':w,'attempt':p['attempt'],'output_path':str(o.relative_to(self.root)),'result_hash':sha(o.read_bytes()),'completed_at':iso(now())}
  if not self.out(p).exists():self.write(self.out(p),res)
  s=self.state();s['completed_assignments'][key(p)]=res;self.write(self.sp,s);r.unlink();return res
 def recover(self,t=None):
  t=t or now();a=[]
  for r in sorted((self.root/'running').glob('*.json')):
   try:
    p=self.read(r);self.valid(p);e=p.get('lease',{}).get('lease_expires_at')
    if not e:self.quarantine(r,'missing lease');a.append({'status':'QUARANTINED'});continue
    if dt(e)>t:continue
    n=p['attempt']+1;p.pop('lease',None);p['attempt']=n
    if n>=p['max_attempts']:
     p['failure_reason']='lease expired';self.write(self.safe_path('failed',r.name),p);r.unlink();a.append({'status':'FAILED','attempt':n})
    else:
     name=r.name.split('.__owner__')[0]+'.json';self.write(self.safe_path('inbox',name),p);r.unlink();a.append({'status':'REQUEUED','attempt':n})
   except (json.JSONDecodeError,UnicodeDecodeError,Invalid) as e:self.quarantine(r,str(e));a.append({'status':'QUARANTINED'})
  return a
 def scan(self,w):
  self.recover();r=self.claim(w);return {'status':'IDLE'} if r is None else self.execute(r,w)
 def completed_record(self,p):return self.done(p)
 def _outbox_result_path(self,p):return self.out(p)
 def claim_next(self,w,now=None):return self.claim(w,now)
 def execute_claim(self,c,w):return self.execute(c,w)
 def recover_expired(self,now=None):return self.recover(now)
 def scan_once(self,w):return self.scan(w)
LocalRelayDispatcher=Dispatcher
