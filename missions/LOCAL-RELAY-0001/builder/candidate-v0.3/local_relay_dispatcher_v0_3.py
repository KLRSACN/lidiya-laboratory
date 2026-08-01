from relay_common_v0_3 import *
from relay_storage_v0_3 import StorageMixin
from relay_transaction_v0_3 import TransactionMixin
from relay_recovery_v0_3 import RecoveryMixin
class LocalRelayDispatcherV03(StorageMixin,TransactionMixin,RecoveryMixin):
    def claim(self,worker_id,now=None):return self.claim_next(worker_id,now)
LocalRelayDispatcher=LocalRelayDispatcherV03
