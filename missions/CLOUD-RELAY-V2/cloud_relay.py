from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

UTC = timezone.utc
Role = Literal['COORDINATOR', 'BUILDER', 'VERIFIER']
Status = Literal[
    'READY', 'CLAIMED', 'BUILDER_DONE', 'VERIFY_PASS', 'VERIFY_FAIL',
    'PROJECT_DONE', 'NEEDS_BOXUAN_APPROVAL'
]


class RelayError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None) -> str:
    return (dt or utcnow()).isoformat()


def canonical_hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


@dataclass
class MissionState:
    schema_version: int
    mission_id: str
    project_id: str
    cycle: int
    step_id: int
    owner: Role
    status: Status
    goal: str
    acceptance: list[str]
    last_packet_id: str | None
    last_packet_hash: str | None
    lease_owner: Role | None
    lease_until: str | None
    updated_at: str
    completed_steps: list[str]
    next_project_hint: str | None = None

    @classmethod
    def new(cls, mission_id: str, project_id: str, goal: str, acceptance: list[str]) -> 'MissionState':
        return cls(
            schema_version=1,
            mission_id=mission_id,
            project_id=project_id,
            cycle=1,
            step_id=1,
            owner='COORDINATOR',
            status='READY',
            goal=goal,
            acceptance=acceptance,
            last_packet_id=None,
            last_packet_hash=None,
            lease_owner=None,
            lease_until=None,
            updated_at=iso(),
            completed_steps=[],
        )


@dataclass
class RelayPacket:
    schema_version: int
    packet_id: str
    mission_id: str
    run_id: str
    step_id: int
    source: Role
    target: Role
    action: str
    status: str
    payload: dict
    input_hash: str
    created_at: str
    consumed: bool = False
    consumed_at: str | None = None

    @classmethod
    def build(
        cls,
        mission_id: str,
        step_id: int,
        source: Role,
        target: Role,
        action: str,
        payload: dict,
        status: str = 'READY',
    ) -> 'RelayPacket':
        return cls(
            schema_version=1,
            packet_id=f'PKT-{uuid.uuid4().hex[:12].upper()}',
            mission_id=mission_id,
            run_id=f'RUN-{utcnow().strftime("%Y%m%dT%H%M%SZ")}-{uuid.uuid4().hex[:6].upper()}',
            step_id=step_id,
            source=source,
            target=target,
            action=action,
            status=status,
            payload=payload,
            input_hash=canonical_hash(payload),
            created_at=iso(),
        )


class JsonRelayStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / 'MISSION_STATE.json'
        self.packet_path = self.root / 'RELAY_PACKET.json'
        self.evidence_dir = self.root / 'EVIDENCE'
        self.evidence_dir.mkdir(exist_ok=True)

    def save_state(self, state: MissionState) -> None:
        state.updated_at = iso()
        self.state_path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def load_state(self) -> MissionState:
        if not self.state_path.exists():
            raise RelayError('MISSION_STATE.json missing')
        return MissionState(**json.loads(self.state_path.read_text(encoding='utf-8')))

    def save_packet(self, packet: RelayPacket) -> None:
        self.packet_path.write_text(json.dumps(asdict(packet), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def load_packet(self) -> RelayPacket:
        if not self.packet_path.exists():
            raise RelayError('RELAY_PACKET.json missing')
        return RelayPacket(**json.loads(self.packet_path.read_text(encoding='utf-8')))

    def claim(self, role: Role, ttl_seconds: int = 900) -> MissionState:
        state = self.load_state()
        now = utcnow()
        if state.lease_until:
            lease_until = datetime.fromisoformat(state.lease_until)
            if lease_until > now and state.lease_owner != role:
                raise RelayError(f'lease held by {state.lease_owner} until {state.lease_until}')
        state.lease_owner = role
        state.lease_until = iso(now + timedelta(seconds=ttl_seconds))
        state.status = 'CLAIMED'
        self.save_state(state)
        return state

    def release(self, role: Role) -> MissionState:
        state = self.load_state()
        if state.lease_owner not in (None, role):
            raise RelayError(f'lease owned by {state.lease_owner}')
        state.lease_owner = None
        state.lease_until = None
        if state.status == 'CLAIMED':
            state.status = 'READY'
        self.save_state(state)
        return state

    def consume_packet(self, role: Role) -> RelayPacket:
        packet = self.load_packet()
        if packet.target != role:
            raise RelayError(f'packet target is {packet.target}, not {role}')
        if packet.consumed:
            raise RelayError(f'packet already consumed: {packet.packet_id}')
        if canonical_hash(packet.payload) != packet.input_hash:
            raise RelayError('packet hash mismatch')
        packet.consumed = True
        packet.consumed_at = iso()
        self.save_packet(packet)
        state = self.load_state()
        state.last_packet_id = packet.packet_id
        state.last_packet_hash = packet.input_hash
        self.save_state(state)
        return packet

    def write_evidence(self, step_id: int, actor: Role, result: str, details: dict) -> Path:
        evidence = {
            'schema_version': 1,
            'mission_id': self.load_state().mission_id,
            'step_id': step_id,
            'actor': actor,
            'result': result,
            'details': details,
            'evidence_hash': canonical_hash(details),
            'created_at': iso(),
        }
        path = self.evidence_dir / f'STEP-{step_id:04d}-{actor}.json'
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return path


def coordinator_dispatch(store: JsonRelayStore) -> RelayPacket:
    state = store.claim('COORDINATOR')
    try:
        packet = RelayPacket.build(
            mission_id=state.mission_id,
            step_id=state.step_id,
            source='COORDINATOR',
            target='BUILDER',
            action='BUILD',
            payload={
                'goal': state.goal,
                'acceptance': state.acceptance,
                'instruction': 'Perform one minimal, reversible, verifiable step and return evidence.',
            },
        )
        store.save_packet(packet)
        state.owner = 'BUILDER'
        state.status = 'READY'
        store.save_state(state)
        return packet
    finally:
        store.release('COORDINATOR')


def builder_complete(store: JsonRelayStore, result: dict) -> RelayPacket:
    store.claim('BUILDER')
    try:
        incoming = store.consume_packet('BUILDER')
        store.write_evidence(incoming.step_id, 'BUILDER', 'BUILDER_DONE', result)
        packet = RelayPacket.build(
            mission_id=incoming.mission_id,
            step_id=incoming.step_id,
            source='BUILDER',
            target='VERIFIER',
            action='VERIFY',
            payload={'builder_result': result, 'acceptance': store.load_state().acceptance},
            status='BUILDER_DONE',
        )
        store.save_packet(packet)
        state = store.load_state()
        state.owner = 'VERIFIER'
        state.status = 'BUILDER_DONE'
        store.save_state(state)
        return packet
    finally:
        store.release('BUILDER')


def verifier_complete(store: JsonRelayStore, passed: bool, details: dict) -> RelayPacket:
    store.claim('VERIFIER')
    try:
        incoming = store.consume_packet('VERIFIER')
        verdict = 'VERIFY_PASS' if passed else 'VERIFY_FAIL'
        store.write_evidence(incoming.step_id, 'VERIFIER', verdict, details)
        packet = RelayPacket.build(
            mission_id=incoming.mission_id,
            step_id=incoming.step_id,
            source='VERIFIER',
            target='COORDINATOR' if passed else 'BUILDER',
            action='ACCEPT' if passed else 'REPAIR',
            payload={'verdict': verdict, 'details': details},
            status=verdict,
        )
        store.save_packet(packet)
        state = store.load_state()
        state.owner = packet.target
        state.status = verdict
        if passed:
            state.completed_steps.append(f'STEP-{state.step_id:04d}')
            state.step_id += 1
        store.save_state(state)
        return packet
    finally:
        store.release('VERIFIER')
