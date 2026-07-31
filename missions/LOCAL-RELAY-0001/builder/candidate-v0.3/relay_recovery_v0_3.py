from __future__ import annotations
import json
from datetime import datetime
from relay_common_v0_3 import *

class RecoveryMixin:
    def recover_expired(self, now=None):
        current=now or utc_now(); actions=[]
        for running in sorted(self.safe_path('running').glob('*.json')):
            try:
                packet=self.read_json(running); self.validate_packet(packet); lease=packet.get('lease') or {}; expires=lease.get('lease_expires_at')
                if not expires: self._quarantine_path(running,'missing lease'); actions.append({'status':'QUARANTINED'}); continue
                if parse_dt(expires)>current: continue
                reconciliation=self._reconcile_assignment(packet)
                if reconciliation in {'COMPLETED','REPAIRED'}:
                    running.unlink(missing_ok=True); actions.append({'status':'COMPLETED_BY_RECONCILIATION'}); continue
                packet['attempt']+=1; packet['recovery_count']=packet.get('recovery_count',0)+1; packet.pop('lease',None)
                if packet['attempt']>=packet['max_attempts']:
                    packet['failure_reason']='lease expired'; self.atomic_json_write(self.safe_path('failed',running.name),packet); running.unlink(missing_ok=True)
                    self._set_task_state(packet,'FAILED',{'reason':'lease expired'}); actions.append({'status':'FAILED','attempt':packet['attempt']})
                else:
                    inbox_name=running.name.split('.__owner__',1)[0]+'.json'; self.atomic_json_write(self.safe_path('inbox',inbox_name),packet); running.unlink(missing_ok=True)
                    self._set_task_state(packet,'QUEUED',{'reason':'lease expired'}); actions.append({'status':'REQUEUED','attempt':packet['attempt'],'recovery_count':packet['recovery_count']})
            except (json.JSONDecodeError,UnicodeDecodeError,Invalid,Unsafe) as exc:
                self._quarantine_path(running,str(exc)); actions.append({'status':'QUARANTINED'})
        return actions
    def _identity(self,result): return {k:result[k] for k in ('mission_id','token','task_id')}
    def _reconcile_assignment(self, packet):
        outbox=self.outbox_path(packet); registry=self.completed_record(packet); jp=self.journal_path(packet); journal=self.read_json(jp) if jp.exists() else None; result=None
        if journal: result=journal.get('result')
        if outbox.exists():
            out=self.read_json(outbox); self._validate_result(out)
            if result and result!=out: raise Invalid('journal/outbox conflict')
            result=out
        if registry:
            self._validate_result(registry)
            if result and result!=registry: raise Invalid('registry/result conflict')
            result=registry
        if not result:return 'NONE'
        if self._identity(result)!={k:packet[k] for k in ('mission_id','token','task_id')}: raise Invalid('identity mismatch')
        repaired=False
        if not outbox.exists(): self.atomic_json_write(outbox,result); repaired=True
        if not registry: self._commit_registry(packet,result); repaired=True
        self._write_journal(packet,'COMMITTED',result); return 'REPAIRED' if repaired else 'COMPLETED'
    def reconcile(self):
        actions=[]; identities={}
        for jp in sorted(self.safe_path('state','journal').glob('*.journal.json')):
            try:
                journal=self.read_json(jp); result=journal.get('result')
                if not isinstance(result,dict): raise Invalid('journal result missing')
                if journal.get('result_record_hash')!=sha256_bytes(canonical(result)): raise Invalid('journal hash mismatch')
                packet=self._identity(result); identities[assignment_key(packet)]=packet
            except Exception as exc:
                self._quarantine_path(jp,str(exc)); actions.append({'status':'JOURNAL_QUARANTINED','reason':str(exc)})
        for op in sorted(self.safe_path('outbox').glob('*.result.json')):
            try:
                result=self.read_json(op); packet=self._identity(result); identities[assignment_key(packet)]=packet
            except Exception as exc:
                self._quarantine_path(op,str(exc)); actions.append({'status':'OUTBOX_QUARANTINED','reason':str(exc)})
        for record in self.dispatcher_state().get('completed_assignments',{}).values():
            if isinstance(record,dict):
                try: packet=self._identity(record); identities[assignment_key(packet)]=packet
                except KeyError: pass
        for packet in identities.values():
            try:
                status=self._reconcile_assignment(packet)
                if status=='REPAIRED': actions.append({'status':'REPAIRED','assignment_key':assignment_key(packet)})
            except Exception as exc:
                self.atomic_json_write(self.safe_path('quarantine',f'{assignment_slug(packet)}.reconciliation-error.json'),{'reason':str(exc),'assignment_key':assignment_key(packet)})
                actions.append({'status':'BLOCKED','assignment_key':assignment_key(packet),'reason':str(exc)})
        if actions:
            state=self.dispatcher_state(); state['reconciliation_log'].extend(actions); self._write_state(state)
        return actions
    def recover(self, now=None): return self.recover_expired(now)
    def scan_once(self, worker_id):
        self.reconcile(); self.recover_expired(); claim=self.claim_next(worker_id)
        return {'status':'IDLE'} if claim is None else self.execute_claim(claim,worker_id)
