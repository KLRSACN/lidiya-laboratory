from __future__ import annotations
from relay_common_v0_3 import *
class TransactionMixin:
    def _output(self,p):
        rel=p['payload'].get('relative_output_path','outputs/result.txt')
        from pathlib import Path
        if not isinstance(rel,str) or Path(rel).is_absolute() or '..' in Path(rel).parts:raise Unsafe('path conflict')
        return self.safe_path('state',rel)
    def _result(self,p,worker,cid,out):
        ob=self.outbox_path(p)
        return {'task_id':p['task_id'],'mission_id':p['mission_id'],'token':p['token'],'action':p['action'],'status':'COMPLETED','result_hash':sha256_bytes(out.read_bytes()),'output_path':str(out.relative_to(self.root)),'outbox_path':str(ob.relative_to(self.root)),'completed_at':iso(utc_now()),'claim_id':cid,'lease_generation':p['lease_generation'],'recovery_count':p.get('recovery_count',0),'checkpoint_ref':str(self.checkpoint_file(p['task_id']).relative_to(self.root)),'worker_id':worker}
    def _journal(self,p,phase,result,step):
        self.write_json(self.journal_path(p),{'schema_version':'LOCAL_RELAY_JOURNAL_V0.3','assignment_key':assignment_key(p),'phase':phase,'result':result,'result_record_hash':sha256_bytes(canonical(result)),'highest_progress_token':progress_token(p,step),'updated_at':iso(utc_now())})
    def _validate_result(self,r):
        need={'task_id','mission_id','token','action','result_hash','outbox_path','completed_at','claim_id','lease_generation','recovery_count','checkpoint_ref'}
        if need-set(r):raise Invalid('result schema')
        out=self.safe_path(r['output_path'])
        if not out.exists() or sha256_bytes(out.read_bytes())!=r['result_hash']:raise Invalid('hash conflict')
        if self.safe_path(r['outbox_path']).parent!=self.safe_path('outbox'):raise Invalid('outbox path conflict')
    def _registry(self,p,r):
        s=self.state();k=assignment_key(p);old=s['completed_assignments'].get(k)
        if old and old!=r:raise Invalid('registry conflict')
        s['completed_assignments'][k]=r;self._write_state(s)
    def submit_result(self,claim,worker_id,lease_generation=None,now=None,fault=None):
        path,p=self._live(claim,worker_id,lease_generation,now)
        if self.completed_record(p) or self.outbox_path(p).exists():path.unlink(missing_ok=True);return {'status':'DUPLICATE_COMPLETED'}
        out=self._output(p);text=p['payload'].get('text')
        if not isinstance(text,str):return self.fail_claim(path,p,'text',False)
        placeholder={'task_id':p['task_id'],'mission_id':p['mission_id'],'token':p['token'],'action':p['action'],'status':'PREPARED','result_hash':None,'output_path':str(out.relative_to(self.root)),'outbox_path':str(self.outbox_path(p).relative_to(self.root)),'completed_at':None,'claim_id':p['lease']['claim_id'],'lease_generation':p['lease_generation'],'recovery_count':p.get('recovery_count',0),'checkpoint_ref':str(self.checkpoint_file(p['task_id']).relative_to(self.root)),'worker_id':worker_id}
        self._journal(p,'PREPARED',placeholder,3)
        if fault=='after_prepared_before_side_effect':raise FaultInjected(fault)
        self.atomic_write(out,text.encode())
        if fault=='after_side_effect_before_result':raise FaultInjected(fault)
        r=self._result(p,worker_id,p['lease']['claim_id'],out);self._journal(p,'RESULT_PERSISTED',r,4)
        if fault=='after_result_before_outbox':raise FaultInjected(fault)
        self.write_json(self.outbox_path(p),r)
        if fault=='after_outbox_before_registry':raise FaultInjected(fault)
        self._registry(p,r)
        if fault=='after_registry_before_committed':raise FaultInjected(fault)
        self._journal(p,'COMMITTED',r,5);self._task_record(p,'completed',result_hash=r['result_hash'],outbox_path=r['outbox_path'],highest_progress_token=progress_token(p,5));self._checkpoint(p,'completed',worker_id,p['lease']['claim_id'],r['result_hash'],5)
        if fault=='after_committed_before_running_cleanup':raise FaultInjected(fault)
        path.unlink(missing_ok=True);return r
    execute_claim=submit_result
    def fail_claim(self,path,p,reason,terminal=False):
        p['attempt']+=1;p.pop('lease',None)
        if terminal or p['attempt']>=p['max_attempts']:
            p['failure_reason']=reason;self.write_json(self.safe_path('failed',path.name),p);path.unlink(missing_ok=True);self._task_record(p,'failed',reason=reason,highest_progress_token=progress_token(p,6));self._checkpoint(p,'failed',result_hash=None,step=6);return {'status':'FAILED'}
        self.write_json(self.safe_path('inbox',path.name.split('.__owner__')[0]+'.json'),p);path.unlink(missing_ok=True);self._task_record(p,'pending',highest_progress_token=progress_token(p,0));return {'status':'RETRY_SCHEDULED'}
