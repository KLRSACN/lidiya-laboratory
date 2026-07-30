from __future__ import annotations
import json,os,tempfile,uuid
from datetime import datetime,timedelta
from pathlib import Path
from typing import Any
from relay_common_v0_2 import *
class StorageMixin:

    def __init__(self, runtime_root: str | Path):
        self.root = Path(runtime_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in DIRS:
            self.safe_path(directory).mkdir(parents=True, exist_ok=True)
        self.state_path = self.safe_path('state', 'dispatcher_state.json')
        if not self.state_path.exists():
            self.atomic_json_write(self.state_path, {'completed_assignments': {}, 'reconciliation_log': []})
        self.reconcile()

    def safe_path(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise Unsafe('path escape') from exc
        return path

    def _assert_under_root(self, path: Path) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise Unsafe('path escape') from exc
        return resolved

    def atomic_write_bytes(self, path: Path, data: bytes) -> None:
        path = self._assert_under_root(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def atomic_json_write(self, path: Path, value: dict[str, Any]) -> None:
        payload = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')
        self.atomic_write_bytes(path, payload)

    def read_json(self, path: Path) -> dict[str, Any]:
        path = self._assert_under_root(path)
        with path.open('r', encoding='utf-8') as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise Invalid('root not object')
        return value

    def validate_packet(self, packet: dict[str, Any]) -> None:
        missing = REQ - set(packet)
        if missing:
            raise Invalid('missing:' + ','.join(sorted(missing)))
        if packet['action'] != 'WRITE_TEXT':
            raise Invalid('unsupported action')
        if not isinstance(packet['payload'], dict):
            raise Invalid('payload')
        if not isinstance(packet['attempt'], int) or packet['attempt'] < 0:
            raise Invalid('attempt')
        if not isinstance(packet['max_attempts'], int) or packet['max_attempts'] < 1:
            raise Invalid('max_attempts')
        if packet['attempt'] > packet['max_attempts']:
            raise Invalid('attempt exceeds max_attempts')
        if not isinstance(packet['lease_seconds'], int) or packet['lease_seconds'] < 1:
            raise Invalid('lease')
        if packet.get('packet_sha256') and packet['packet_sha256'] != packet_hash(packet):
            raise Invalid('hash')

    def enqueue(self, packet: dict[str, Any], name: str | None=None) -> Path:
        self.validate_packet(packet)
        name = name or f'{assignment_slug(packet)}.json'
        if Path(name).name != name:
            raise Unsafe('filename')
        destination = self.safe_path('inbox', name)
        self.atomic_json_write(destination, packet)
        return destination

    def dispatcher_state(self) -> dict[str, Any]:
        return self.read_json(self.state_path)

    def _write_state(self, state: dict[str, Any]) -> None:
        self.atomic_json_write(self.state_path, state)

    def outbox_path(self, packet: dict[str, Any]) -> Path:
        return self.safe_path('outbox', f'{assignment_slug(packet)}.result.json')

    def journal_path(self, packet: dict[str, Any]) -> Path:
        return self.safe_path('state', 'journal', f'{assignment_slug(packet)}.journal.json')

    def checkpoint_path(self, running_path: Path) -> Path:
        return self.safe_path('checkpoints', f'{running_path.stem}.checkpoint.json')

    def completed_record(self, packet: dict[str, Any]) -> dict[str, Any] | None:
        return self.dispatcher_state()['completed_assignments'].get(assignment_key(packet))

    def _quarantine_path(self, source: Path, reason: str) -> Path:
        source = self._assert_under_root(source)
        target = self.safe_path('quarantine', source.name)
        if target.exists():
            target = self.safe_path('quarantine', f'{source.stem}.{uuid.uuid4().hex}.json')
        os.replace(source, target)
        self.atomic_json_write(self.safe_path('quarantine', f'{target.name}.reason.json'), {'reason': reason})
        return target

    def claim_next(self, worker_id: str, now: datetime | None=None) -> Claim | None:
        current = now or utc_now()
        for source in sorted(self.safe_path('inbox').glob('*.json')):
            claim_id = uuid.uuid4().hex
            running = self.safe_path('running', f'{source.stem}.__owner__{worker_id}.__claim__{claim_id}.json')
            try:
                os.replace(source, running)
            except OSError:
                continue
            try:
                packet = self.read_json(running)
                self.validate_packet(packet)
                if packet['target_worker'] not in (worker_id, 'ANY'):
                    os.replace(running, source)
                    continue
                if self.completed_record(packet) or self.outbox_path(packet).exists():
                    duplicate = self.safe_path('outbox', f'{source.stem}.duplicate.json')
                    if not duplicate.exists():
                        self.atomic_json_write(duplicate, {'status': 'DUPLICATE_COMPLETED', 'assignment_key': assignment_key(packet)})
                    running.unlink(missing_ok=True)
                    return None
                lease = {'owner': worker_id, 'claim_id': claim_id, 'claimed_at': iso(current), 'heartbeat_at': iso(current), 'lease_expires_at': iso(current + timedelta(seconds=packet['lease_seconds']))}
                packet['lease'] = lease
                self.atomic_json_write(running, packet)
                self.atomic_json_write(self.checkpoint_path(running), {'assignment_key': assignment_key(packet), 'owner': worker_id, 'claim_id': claim_id, 'current_state': 'RUNNING', 'attempt': packet['attempt'], 'lease_expires_at': lease['lease_expires_at']})
                return Claim(running, packet, worker_id, claim_id)
            except (json.JSONDecodeError, UnicodeDecodeError, Invalid) as exc:
                self._quarantine_path(running, str(exc))
        return None

    def _validate_live_claim(self, claim: Claim | Path, worker_id: str, now: datetime | None=None) -> tuple[Path, dict[str, Any]]:
        current = now or utc_now()
        if isinstance(claim, Claim):
            path = claim.path
            expected_claim_id = claim.claim_id
        else:
            path = Path(claim)
            expected_claim_id = None
        path = self._assert_under_root(path)
        try:
            path.relative_to(self.safe_path('running'))
        except ValueError as exc:
            raise Invalid('not running path') from exc
        if not path.exists():
            raise Invalid('stale owner: claim no longer exists')
        packet = self.read_json(path)
        self.validate_packet(packet)
        lease = packet.get('lease') or {}
        if lease.get('owner') != worker_id:
            raise Invalid('stale owner: owner mismatch')
        if expected_claim_id and lease.get('claim_id') != expected_claim_id:
            raise Invalid('stale owner: claim id mismatch')
        if not lease.get('lease_expires_at') or parse_dt(lease['lease_expires_at']) <= current:
            raise Invalid('stale owner: lease expired')
        return (path, packet)

    def heartbeat(self, claim: Claim | Path, worker_id: str, now: datetime | None=None) -> dict[str, Any]:
        current = now or utc_now()
        path, packet = self._validate_live_claim(claim, worker_id, current)
        packet['lease']['heartbeat_at'] = iso(current)
        packet['lease']['lease_expires_at'] = iso(current + timedelta(seconds=packet['lease_seconds']))
        self.atomic_json_write(path, packet)
        return packet

    def _safe_output_path(self, packet: dict[str, Any]) -> Path:
        relative = packet['payload'].get('relative_output_path', 'outputs/result.txt')
        if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise Unsafe('path traversal')
        return self.safe_path('state', relative)
