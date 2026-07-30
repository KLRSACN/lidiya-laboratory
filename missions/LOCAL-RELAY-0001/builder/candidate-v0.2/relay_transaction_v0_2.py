from __future__ import annotations
import json,os,tempfile,uuid
from datetime import datetime,timedelta
from pathlib import Path
from typing import Any
from relay_common_v0_2 import *
class TransactionMixin:

    def _result_from_effect(self, packet: dict[str, Any], worker_id: str, claim_id: str, output_path: Path) -> dict[str, Any]:
        return {'status': 'COMPLETED', 'mission_id': packet['mission_id'], 'token': packet['token'], 'task_id': packet['task_id'], 'worker_id': worker_id, 'claim_id': claim_id, 'attempt': packet['attempt'], 'output_path': str(output_path.relative_to(self.root)), 'result_hash': sha256_bytes(output_path.read_bytes()), 'completed_at': iso(utc_now())}

    def _write_journal(self, packet: dict[str, Any], phase: str, result: dict[str, Any]) -> None:
        self.atomic_json_write(self.journal_path(packet), {'assignment_key': assignment_key(packet), 'phase': phase, 'packet_identity': {'mission_id': packet['mission_id'], 'token': packet['token'], 'task_id': packet['task_id']}, 'result': result, 'result_record_hash': sha256_bytes(canonical(result)), 'updated_at': iso(utc_now())})

    def _validate_result(self, result: dict[str, Any]) -> None:
        required = {'status', 'mission_id', 'token', 'task_id', 'output_path', 'result_hash'}
        if required - set(result):
            raise Invalid('invalid result record')
        output = self.safe_path(result['output_path'])
        if not output.exists() or sha256_bytes(output.read_bytes()) != result['result_hash']:
            raise Invalid('result hash mismatch')

    def _commit_registry(self, packet: dict[str, Any], result: dict[str, Any]) -> None:
        state = self.dispatcher_state()
        existing = state['completed_assignments'].get(assignment_key(packet))
        if existing and existing != result:
            raise Invalid('registry conflict')
        state['completed_assignments'][assignment_key(packet)] = result
        self._write_state(state)

    def execute_claim(self, claim: Claim | Path, worker_id: str, now: datetime | None=None, fault: str | None=None) -> dict[str, Any]:
        path, packet = self._validate_live_claim(claim, worker_id, now)
        existing = self.completed_record(packet)
        outbox = self.outbox_path(packet)
        if existing or outbox.exists():
            path.unlink(missing_ok=True)
            return {'status': 'DUPLICATE_COMPLETED'}
        try:
            output_path = self._safe_output_path(packet)
        except Unsafe:
            return self.fail_claim(path, packet, 'path traversal', terminal=True)
        text = packet['payload'].get('text')
        if not isinstance(text, str):
            return self.fail_claim(path, packet, 'text', terminal=False)
        claim_id = packet['lease']['claim_id']
        journal = self.journal_path(packet)
        if journal.exists():
            journal_record = self.read_json(journal)
            result = journal_record.get('result')
            if not isinstance(result, dict):
                raise Invalid('journal result missing')
            self._validate_result(result)
        else:
            self.atomic_write_bytes(output_path, text.encode('utf-8'))
            result = self._result_from_effect(packet, worker_id, claim_id, output_path)
            self._write_journal(packet, 'PREPARED', result)
        if fault == 'after_journal_before_outbox':
            raise FaultInjected('after_journal_before_outbox')
        if not outbox.exists():
            self.atomic_json_write(outbox, result)
        if fault == 'after_outbox_before_registry':
            raise FaultInjected('after_outbox_before_registry')
        self._commit_registry(packet, result)
        if fault == 'after_registry_before_journal_commit':
            raise FaultInjected('after_registry_before_journal_commit')
        self._write_journal(packet, 'COMMITTED', result)
        path.unlink(missing_ok=True)
        return result

    def fail_claim(self, running_path: Path, packet: dict[str, Any], reason: str, terminal: bool=False) -> dict[str, Any]:
        next_attempt = packet['attempt'] + 1
        packet.pop('lease', None)
        packet['attempt'] = next_attempt
        packet['failure_reason'] = reason
        if terminal or next_attempt >= packet['max_attempts']:
            failed = self.safe_path('failed', running_path.name)
            self.atomic_json_write(failed, packet)
            running_path.unlink(missing_ok=True)
            return {'status': 'FAILED', 'attempt': next_attempt}
        inbox_name = running_path.name.split('.__owner__', 1)[0] + '.json'
        packet.pop('failure_reason', None)
        self.atomic_json_write(self.safe_path('inbox', inbox_name), packet)
        running_path.unlink(missing_ok=True)
        return {'status': 'RETRY_SCHEDULED', 'attempt': next_attempt}
