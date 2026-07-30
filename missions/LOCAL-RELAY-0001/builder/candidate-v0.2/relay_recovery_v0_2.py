from __future__ import annotations
import json,os,tempfile,uuid
from datetime import datetime,timedelta
from pathlib import Path
from typing import Any
from relay_common_v0_2 import *
class RecoveryMixin:

    def recover_expired(self, now: datetime | None=None) -> list[dict[str, Any]]:
        current = now or utc_now()
        actions: list[dict[str, Any]] = []
        for running in sorted(self.safe_path('running').glob('*.json')):
            try:
                packet = self.read_json(running)
                self.validate_packet(packet)
                lease = packet.get('lease') or {}
                expires = lease.get('lease_expires_at')
                if not expires:
                    self._quarantine_path(running, 'missing lease')
                    actions.append({'status': 'QUARANTINED'})
                    continue
                if parse_dt(expires) > current:
                    continue
                reconciliation = self._reconcile_assignment(packet)
                if reconciliation in {'COMPLETED', 'REPAIRED'}:
                    running.unlink(missing_ok=True)
                    actions.append({'status': 'COMPLETED_BY_RECONCILIATION'})
                    continue
                next_attempt = packet['attempt'] + 1
                packet.pop('lease', None)
                packet['attempt'] = next_attempt
                if next_attempt >= packet['max_attempts']:
                    packet['failure_reason'] = 'lease expired'
                    self.atomic_json_write(self.safe_path('failed', running.name), packet)
                    running.unlink(missing_ok=True)
                    actions.append({'status': 'FAILED', 'attempt': next_attempt})
                else:
                    inbox_name = running.name.split('.__owner__', 1)[0] + '.json'
                    self.atomic_json_write(self.safe_path('inbox', inbox_name), packet)
                    running.unlink(missing_ok=True)
                    actions.append({'status': 'REQUEUED', 'attempt': next_attempt})
            except (json.JSONDecodeError, UnicodeDecodeError, Invalid, Unsafe) as exc:
                self._quarantine_path(running, str(exc))
                actions.append({'status': 'QUARANTINED'})
        return actions

    def _packet_identity_from_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return {'mission_id': result['mission_id'], 'token': result['token'], 'task_id': result['task_id']}

    def _reconcile_assignment(self, packet: dict[str, Any]) -> str:
        outbox = self.outbox_path(packet)
        registry = self.completed_record(packet)
        journal_path = self.journal_path(packet)
        journal = self.read_json(journal_path) if journal_path.exists() else None
        result = None
        if journal:
            result = journal.get('result')
        if outbox.exists():
            outbox_result = self.read_json(outbox)
            self._validate_result(outbox_result)
            if result and result != outbox_result:
                raise Invalid('journal/outbox conflict')
            result = outbox_result
        if registry:
            self._validate_result(registry)
            if result and result != registry:
                raise Invalid('registry/result conflict')
            result = registry
        if not result:
            return 'NONE'
        identity = self._packet_identity_from_result(result)
        if identity != {k: packet[k] for k in ('mission_id', 'token', 'task_id')}:
            raise Invalid('identity mismatch')
        repaired = False
        if not outbox.exists():
            self.atomic_json_write(outbox, result)
            repaired = True
        if not registry:
            self._commit_registry(packet, result)
            repaired = True
        self._write_journal(packet, 'COMMITTED', result)
        return 'REPAIRED' if repaired else 'COMPLETED'

    def reconcile(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        identities: dict[str, dict[str, Any]] = {}
        for journal_path in sorted(self.safe_path('state', 'journal').glob('*.journal.json')):
            try:
                journal = self.read_json(journal_path)
                result = journal.get('result')
                if not isinstance(result, dict):
                    raise Invalid('journal result missing')
                if journal.get('result_record_hash') != sha256_bytes(canonical(result)):
                    raise Invalid('journal hash mismatch')
                packet = self._packet_identity_from_result(result)
                identities[assignment_key(packet)] = packet
            except (json.JSONDecodeError, UnicodeDecodeError, Invalid, Unsafe) as exc:
                self._quarantine_path(journal_path, str(exc))
                actions.append({'status': 'JOURNAL_QUARANTINED', 'reason': str(exc)})
        for outbox_path in sorted(self.safe_path('outbox').glob('*.result.json')):
            try:
                result = self.read_json(outbox_path)
                packet = self._packet_identity_from_result(result)
                identities[assignment_key(packet)] = packet
            except (json.JSONDecodeError, UnicodeDecodeError, Invalid, Unsafe) as exc:
                self._quarantine_path(outbox_path, str(exc))
                actions.append({'status': 'OUTBOX_QUARANTINED', 'reason': str(exc)})
        state = self.dispatcher_state()
        for record in state.get('completed_assignments', {}).values():
            if isinstance(record, dict):
                try:
                    packet = self._packet_identity_from_result(record)
                    identities[assignment_key(packet)] = packet
                except KeyError:
                    continue
        for packet in identities.values():
            try:
                status = self._reconcile_assignment(packet)
                if status == 'REPAIRED':
                    actions.append({'status': 'REPAIRED', 'assignment_key': assignment_key(packet)})
            except (Invalid, Unsafe, json.JSONDecodeError, UnicodeDecodeError) as exc:
                diagnostic = self.safe_path('quarantine', f'{assignment_slug(packet)}.reconciliation-error.json')
                self.atomic_json_write(diagnostic, {'reason': str(exc), 'assignment_key': assignment_key(packet)})
                actions.append({'status': 'BLOCKED', 'assignment_key': assignment_key(packet), 'reason': str(exc)})
        if actions:
            state = self.dispatcher_state()
            state.setdefault('reconciliation_log', []).extend(actions)
            self._write_state(state)
        return actions

    def scan_once(self, worker_id: str) -> dict[str, Any]:
        self.reconcile()
        self.recover_expired()
        claim = self.claim_next(worker_id)
        return {'status': 'IDLE'} if claim is None else self.execute_claim(claim, worker_id)
