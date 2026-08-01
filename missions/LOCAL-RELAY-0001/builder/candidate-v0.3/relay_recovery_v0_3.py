from __future__ import annotations
import json
from relay_common_v0_3 import *
class RecoveryMixin:
    def _identity(self,r):return {k:r[k] for k in ('mission_id','token','task_id')}
    def _reconcile_one(self,p):
        jp=self.journal_path(p);op=self.outbox_path(p);reg=self.completed_record(p);j=self.read_json(jp) if jp.exists() else None;r=None
        if j and j.get('phase')!='PREPARED':
            if j.get('result_record_hash')!=sha256_bytes(canonical(j['result'])):raise Invalid('journal hash conflict')
            r=j['result']
        if op.exists():
            o=self.read_json(op);self._validate_result(o)
            if r and r!=o:raise Invalid('outbox conflict')
            r=o
        if reg:
            self._validate_result(reg)
            if r and r!=reg:raise Invalid('registry conflict')
            r=reg
        if not r:return 'NONE'
        if self._identity(r)!={k:p[k] for k in ('mission_id','token','task_id')}:raise Invalid('identity conflict')
        if not op.exists():self.write_json(op,r)
        if not reg:self._registry(p,r)
        tr=self.read_task_state(p['task_id']);full={**p,'action':r.get('action','WRITE_TEXT'),'attempt':tr['attempt'] if tr else 0,'lease_generation':r.get('lease_generation',tr['lease_generation'] if tr else 0),'recovery_count':r.get('recovery_count',tr['recovery_count'] if tr else 0)};self._journal(full,'COMMITTED',r,5);self._task_record(full,'completed',result_hash=r['result_hash'],outbox_path=r['outbox_path'],highest_progress_token=progress_token(full,5));self._checkpoint(full,'completed',r.get('worker_id'),r.get('claim_id'),r['result_hash'],5)
        return 'COMPLETED'
    def reconcile(self):
        ids={};actions=[]
        for f in list(self.safe_path('state','journal').glob('*.json'))+list(self.safe_path('outbox').glob('*.result.json')):
            try:
                x=self.read_json(f);r=x.get('result',x);p=self._identity(r);ids[assignment_key(p)]=p
            except Exception as e:self.quarantine(f,str(e));actions.append({'status':'BLOCKED','reason':str(e)})
        for r in self.state()['completed_assignments'].values():
            try:p=self._identity(r);ids[assignment_key(p)]=p
            except Exception:pass
        for p in ids.values():
            try:self._reconcile_one(p)
            except Exception as e:
                self.write_json(self.safe_path('quarantine',slug(p)+'.reconciliation-error.json'),{'reason':str(e)});tr=self.read_task_state(p['task_id']);base={'mission_id':p['mission_id'],'token':p['token'],'task_id':p['task_id'],'action':tr['action'] if tr else 'WRITE_TEXT','attempt':tr['attempt'] if tr else 0,'lease_generation':tr['lease_generation'] if tr else 0,'recovery_count':tr['recovery_count'] if tr else 0};self._task_record(base,'blocked',reason=str(e),highest_progress_token=progress_token(base,7));actions.append({'status':'BLOCKED','reason':str(e)})
        s=self.state();s['last_reconciliation_at']=iso(utc_now());self._write_state(s);return actions
    def recover(self,now=None):
        current=now or utc_now();actions=[]
        for run in sorted(self.safe_path('running').glob('*.json')):
            try:
                p=self.read_json(run);self.validate_packet(p);l=p.get('lease') or {}
                if parse_iso(l['lease_expires_at'])>current:continue
                if self._reconcile_one(p)=='COMPLETED':run.unlink(missing_ok=True);actions.append({'status':'COMPLETED_BY_RECONCILIATION'});continue
                p['attempt']+=1;p['recovery_count']=p.get('recovery_count',0)+1;p.pop('lease',None)
                if p['attempt']>=p['max_attempts']:
                    self.write_json(self.safe_path('failed',run.name),p);run.unlink();self._task_record(p,'failed',reason='lease expired',highest_progress_token=progress_token(p,6));actions.append({'status':'FAILED'})
                else:
                    self.write_json(self.safe_path('inbox',run.name.split('.__owner__')[0]+'.json'),p);run.unlink();self._task_record(p,'pending',highest_progress_token=progress_token(p,0));self._checkpoint(p,'pending',step=0);actions.append({'status':'REQUEUED','recovery_count':p['recovery_count']})
            except Exception as e:self.quarantine(run,str(e));actions.append({'status':'BLOCKED'})
        return actions
    recover_expired=recover
    def scan_once(self,worker_id):
        self.reconcile();self.recover();c=self.claim_next(worker_id);return {'status':'IDLE'} if c is None else self.submit_result(c,worker_id,c.lease_generation)
