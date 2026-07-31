from __future__ import annotations
from pathlib import Path
from relay_common_v0_3 import *

class TransactionMixin:
    def _result_from_effect(self, packet, worker_id, claim_id, output_path):
        outbox_rel=str(self.outbox_path(packet).relative_to(self.root))
        return {'status':'COMPLETED','mission_id':packet['mission_id'],'token':packet['token'],'task_id':packet['task_id'],
                'worker_id':worker_id,'claim_id':claim_id,'lease_generation':packet['lease_generation'],
                'recovery_count':packet.get('recovery_count',0),'attempt':packet['attempt'],
                'output_path':str(output_path.relative_to(self.root)),'outbox_path':outbox_rel,
                'result_hash':sha256_bytes(output_path.read_bytes()),'completed_at':iso(utc_now())}
    def _write_journal(self, packet, phase, result):
        self.atomic_json_write(self.journal_path(packet),{'assignment_key':assignment_key(packet),'phase':phase,
            'packet_identity':{k:packet[k] for k in ('mission_id','token','task_id')},'lease_generation':packet.get('lease_generation',0),
            'result':result,'result_record_hash':sha256_bytes(canonical(result)),'updated_at':iso(utc_now())})
    def _validate_result(self, result):
        required={'status','mission_id','token','task_id','output_path','outbox_path','result_hash','lease_generation'}
        if required-set(result): raise Invalid('invalid result record')
        output=self.safe_path(result['output_path'])
        if not output.exists() or sha256_bytes(output.read_bytes())!=result['result_hash']: raise Invalid('result hash mismatch')
        expected=self.safe_path(result['outbox_path'])
        if expected.parent != self.safe_path('outbox'): raise Invalid('outbox path invalid')
    def _commit_registry(self, packet, result):
        state=self.dispatcher_state(); existing=state['completed_assignments'].get(assignment_key(packet))
        if existing and existing!=result: raise Invalid('registry conflict')
        state['completed_assignments'][assignment_key(packet)]=result
        state['task_states'][assignment_key(packet)]={'mission_id':packet['mission_id'],'token':packet['token'],'task_id':packet['task_id'],
            'status':'COMPLETED','attempt':packet.get('attempt',result.get('attempt',0)),'lease_generation':packet.get('lease_generation',result.get('lease_generation',0)),
            'recovery_count':packet.get('recovery_count',result.get('recovery_count',0)),'details':{'outbox_path':result['outbox_path'],'result_hash':result['result_hash']},
            'updated_at':iso(utc_now())}
        self._write_state(state)
    def execute_claim(self, claim, worker_id, now=None, fault=None):
        path,packet=self._validate_live_claim(claim,worker_id,now)
        if self.completed_record(packet) or self.outbox_path(packet).exists():
            path.unlink(missing_ok=True); return {'status':'DUPLICATE_COMPLETED'}
        try: output_path=self._safe_output_path(packet)
        except Unsafe: return self.fail_claim(path,packet,'path traversal',True)
        text=packet['payload'].get('text')
        if not isinstance(text,str): return self.fail_claim(path,packet,'text',False)
        claim_id=packet['lease']['claim_id']; journal=self.journal_path(packet)
        if journal.exists():
            record=self.read_json(journal); result=record.get('result')
            if not isinstance(result,dict): raise Invalid('journal result missing')
            self._validate_result(result)
            if result.get('lease_generation') != packet['lease_generation']: raise Invalid('journal generation mismatch')
        else:
            self.atomic_write_bytes(output_path,text.encode()); result=self._result_from_effect(packet,worker_id,claim_id,output_path)
            self._write_journal(packet,'PREPARED',result)
        if fault=='after_journal_before_outbox': raise FaultInjected(fault)
        if not self.outbox_path(packet).exists(): self.atomic_json_write(self.outbox_path(packet),result)
        if fault=='after_outbox_before_registry': raise FaultInjected(fault)
        self._commit_registry(packet,result)
        if fault=='after_registry_before_journal_commit': raise FaultInjected(fault)
        self._write_journal(packet,'COMMITTED',result); self._write_checkpoint(path,packet,'COMPLETED','none',['atomic_claim','effect','journal','outbox','registry'],[])
        path.unlink(missing_ok=True); return result
    def submit_result(self, claim, worker_id, now=None, fault=None): return self.execute_claim(claim,worker_id,now,fault)
    def fail_claim(self, running_path, packet, reason, terminal=False):
        next_attempt=packet['attempt']+1; packet.pop('lease',None); packet['attempt']=next_attempt; packet['failure_reason']=reason
        if terminal or next_attempt>=packet['max_attempts']:
            self.atomic_json_write(self.safe_path('failed',running_path.name),packet); running_path.unlink(missing_ok=True)
            self._set_task_state(packet,'FAILED',{'reason':reason}); return {'status':'FAILED','attempt':next_attempt}
        packet.pop('failure_reason',None); packet['recovery_count']=packet.get('recovery_count',0)+1
        inbox_name=running_path.name.split('.__owner__',1)[0]+'.json'; self.atomic_json_write(self.safe_path('inbox',inbox_name),packet); running_path.unlink(missing_ok=True)
        self._set_task_state(packet,'QUEUED',{'reason':reason}); return {'status':'RETRY_SCHEDULED','attempt':next_attempt}
