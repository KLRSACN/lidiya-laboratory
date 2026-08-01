class AuditorAdapter:
    def __init__(self,dispatcher):self.d=dispatcher
    def claim(self,worker_id,now=None):return self.d.claim(worker_id,now)
    def heartbeat(self,claim,worker_id,lease_generation,now=None):return self.d.heartbeat(claim,worker_id,lease_generation,now)
    def submit_result(self,claim,worker_id,lease_generation,now=None,fault=None):return self.d.submit_result(claim,worker_id,lease_generation,now,fault)
    def recover(self,now=None):return self.d.recover(now)
    def read_task_state(self,task_id):return self.d.read_task_state(task_id)
    def read_checkpoint(self,task_id):return self.d.read_checkpoint(task_id)
    def read_completed_record(self,task_id):return self.d.read_completed_record(task_id)
