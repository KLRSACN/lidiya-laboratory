from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from gearbox_controller import GearboxGuardError
from gearbox_authority_experience_signer_shadow_v01 import (
    SCHEMA as SIGNER_SCHEMA,
    SignerTrustSnapshot,
    sign_for_regression,
    verify_signed_authority,
)
from gearbox_external_monotonic_provider_shadow_v01 import (
    ExternalMonotonicProvider,
    MonotonicReceipt,
    ProviderBinding,
    require_external_binding,
    verify_monotonic_receipt,
)
from gearbox_secretary_runtime_freshness_shadow_v01 import (
    SECRETARY_KEY_SHA256,
    SecretaryFreshnessGuardError,
    _canonical_bytes,
    _validate_secret,
)
from gearbox_secretary_signal_shadow_v01 import (
    MISSION_ID,
    NEUTRAL_PRESSURE,
    PINNED_STEP_ID,
    SecretarySignalEnvelope,
    SecretarySignalProjection,
    neutral_secretary_projection,
)
from gearbox_signer_epoch_recovery_shadow_v01 import TrustRootState

SCHEMA = "1.0-shadow"
CLOCK_EPOCH_SCHEMA = "1.0-shadow"
CLOCK_RECEIPT_SCHEMA = "1.0-shadow"
CLOCK_CHECKPOINT_SCHEMA = "1.0-shadow"
EPOCH_OBSERVATION_SCHEMA = "1.0-shadow"
CLOCK_SOURCE_ROLE = "RUNTIME_CLOCK_PROVIDER_SHADOW_V3"
CLOCK_PROVIDER_ID = "QUANTUM_RUNTIME_CLOCK_PROVIDER_EPOCH_V01"
SECRETARY_SIGNER_ID = "W07_SECRETARY_SIGNER_EPOCH_SHADOW_V01"
GENESIS = "GENESIS"
ZERO_HASH = "0" * 64
GIT_BLOB_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SYNTHETIC_CLOCK_KEYS = {
    "clock-epoch-1": b"shadow-runtime-clock-epoch-key-v1-000001",
    "clock-epoch-2": b"shadow-runtime-clock-epoch-key-v2-000002",
}


class ClockEpochRecoveryGuardError(GearboxGuardError):
    pass


def _canon(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _sha256(value: Any, *, name: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise ClockEpochRecoveryGuardError(f"{name} must be 64-hex sha256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ClockEpochRecoveryGuardError(f"{name} must be 64-hex sha256") from exc
    return value.lower()


def _token(value: Any, *, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value.strip()) > 128:
        raise ClockEpochRecoveryGuardError(f"{name} must be explicit bounded string")
    return value.strip()


def _git_blob(value: Any) -> str:
    if type(value) is not str or not GIT_BLOB_RE.fullmatch(value):
        raise ClockEpochRecoveryGuardError("fresh mission blob must be 40-hex git sha")
    return value.lower()


def _clock_key(epoch: str) -> bytes:
    try:
        return SYNTHETIC_CLOCK_KEYS[epoch]
    except KeyError as exc:
        raise ClockEpochRecoveryGuardError("unknown synthetic clock epoch") from exc


def _clock_key_id(epoch: str) -> str:
    return f"runtime-clock-{epoch}"


def _clock_key_sha(epoch: str) -> str:
    return hashlib.sha256(_clock_key(epoch)).hexdigest()


def _external_binding(provider: ExternalMonotonicProvider, *, installation_id: str,
                      runtime_id: str, local_domain: str) -> ProviderBinding:
    try:
        return require_external_binding(
            provider,
            installation_id=installation_id,
            runtime_id=runtime_id,
            forbidden_local_durability_domain_id=local_domain,
        )
    except ValueError as exc:
        raise ClockEpochRecoveryGuardError(str(exc)) from exc


def _receipt(value: Any) -> MonotonicReceipt:
    if isinstance(value, MonotonicReceipt):
        return value
    if not isinstance(value, Mapping):
        raise ClockEpochRecoveryGuardError("provider receipt required")
    try:
        return MonotonicReceipt(**dict(value))
    except TypeError as exc:
        raise ClockEpochRecoveryGuardError("malformed provider receipt") from exc


@dataclass(frozen=True)
class ClockEpochTrustSnapshot:
    schema_version: str
    mission_id: str
    step_id: int
    snapshot_id: str
    clock_epoch_id: str
    clock_key_id: str
    clock_key_sha256: str
    previous_clock_epoch_sha256: str
    revoked_clock_epochs: tuple[str, ...]
    signer_trust_snapshot_id: str
    authority_key_epoch: str
    signature: str

    def unsigned(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("signature")
        data["revoked_clock_epochs"] = list(self.revoked_clock_epochs)
        return data

    @classmethod
    def verify(cls, value: Any, signer_trust_value: Any) -> "ClockEpochTrustSnapshot":
        signer_trust = SignerTrustSnapshot.verify(signer_trust_value)
        if not isinstance(value, Mapping):
            raise ClockEpochRecoveryGuardError("ClockEpochTrustSnapshot required")
        try:
            raw = cls(**dict(value))
        except TypeError as exc:
            raise ClockEpochRecoveryGuardError("malformed ClockEpochTrustSnapshot") from exc
        if raw.schema_version != CLOCK_EPOCH_SCHEMA or raw.mission_id != MISSION_ID or raw.step_id != PINNED_STEP_ID:
            raise ClockEpochRecoveryGuardError("clock epoch trust snapshot scope mismatch")
        _token(raw.snapshot_id, name="snapshot_id")
        _token(raw.clock_epoch_id, name="clock_epoch_id")
        _sha256(raw.previous_clock_epoch_sha256, name="previous_clock_epoch_sha256")
        if raw.clock_epoch_id in raw.revoked_clock_epochs:
            raise ClockEpochRecoveryGuardError("active clock epoch is revoked")
        if raw.signer_trust_snapshot_id != signer_trust.snapshot_id:
            raise ClockEpochRecoveryGuardError("signer trust snapshot mismatch")
        if raw.authority_key_epoch != signer_trust.authority_active_epoch:
            raise ClockEpochRecoveryGuardError("clock epoch snapshot signer is not current authority epoch")
        if raw.clock_key_id != _clock_key_id(raw.clock_epoch_id):
            raise ClockEpochRecoveryGuardError("clock key id mismatch")
        if not hmac.compare_digest(raw.clock_key_sha256, _clock_key_sha(raw.clock_epoch_id)):
            raise ClockEpochRecoveryGuardError("clock key fingerprint mismatch")
        expected = sign_for_regression(raw.unsigned(), "LCR-A", raw.authority_key_epoch)
        if not hmac.compare_digest(raw.signature, expected):
            raise ClockEpochRecoveryGuardError("invalid clock epoch trust snapshot signature")
        return raw


def sign_clock_epoch_snapshot_for_regression(unsigned: Mapping[str, Any], signer_trust_value: Any) -> ClockEpochTrustSnapshot:
    """Synthetic test helper only; this is not production key protection evidence."""
    signer_trust = SignerTrustSnapshot.verify(signer_trust_value)
    payload = dict(unsigned)
    payload.pop("signature", None)
    payload.setdefault("schema_version", CLOCK_EPOCH_SCHEMA)
    payload.setdefault("mission_id", MISSION_ID)
    payload.setdefault("step_id", PINNED_STEP_ID)
    payload.setdefault("clock_key_id", _clock_key_id(payload["clock_epoch_id"]))
    payload.setdefault("clock_key_sha256", _clock_key_sha(payload["clock_epoch_id"]))
    payload.setdefault("signer_trust_snapshot_id", signer_trust.snapshot_id)
    payload.setdefault("authority_key_epoch", signer_trust.authority_active_epoch)
    payload["signature"] = sign_for_regression(payload, "LCR-A", signer_trust.authority_active_epoch)
    return ClockEpochTrustSnapshot.verify(payload, signer_trust_value)


@dataclass(frozen=True)
class ClockEpochRootState:
    clock_snapshot: Mapping[str, Any]
    clock_snapshot_sha256: str
    signer_trust_snapshot: Mapping[str, Any]
    provider_payload_hash: str
    provider_receipt: MonotonicReceipt
    fresh_mission_state_blob_sha: str
    installation_id: str
    runtime_id: str
    local_durability_domain_id: str
    state: str
    secretary_level: str = "UNKNOWN"
    stale_pressure_carryover_allowed: bool = False
    terminal_hold_carryover_allowed: bool = False
    live_routing_authority_allowed: bool = False
    formal_mutation_allowed: bool = False
    experience_delta: int = 0
    operational_progress_delta: int = 0


def _verify_root(root: ClockEpochRootState, provider: ExternalMonotonicProvider) -> ClockEpochTrustSnapshot:
    signer_trust = SignerTrustSnapshot.verify(root.signer_trust_snapshot)
    clock = ClockEpochTrustSnapshot.verify(root.clock_snapshot, root.signer_trust_snapshot)
    if _hash(dict(root.clock_snapshot)) != root.clock_snapshot_sha256:
        raise ClockEpochRecoveryGuardError("CLOCK_EPOCH_SNAPSHOT_HASH_MISMATCH")
    binding = _external_binding(
        provider,
        installation_id=root.installation_id,
        runtime_id=root.runtime_id,
        local_domain=root.local_durability_domain_id,
    )
    receipt = _receipt(root.provider_receipt)
    if provider.read_floor() != receipt.sequence:
        raise ClockEpochRecoveryGuardError("CLOCK_TRUST_ROOT_ROLLBACK_OR_FLOOR_DIVERGENCE")
    try:
        verify_monotonic_receipt(
            provider,
            receipt,
            expected_binding=binding,
            expected_previous_sequence=receipt.sequence - 1,
            expected_previous_receipt_hash=receipt.previous_receipt_hash,
            expected_payload_hash=root.provider_payload_hash,
        )
    except ValueError as exc:
        raise ClockEpochRecoveryGuardError(str(exc)) from exc
    if clock.signer_trust_snapshot_id != signer_trust.snapshot_id:
        raise ClockEpochRecoveryGuardError("clock/signer trust mismatch")
    return clock


def bootstrap_clock_epoch_from_signer_root(*, signer_root: TrustRootState,
                                           clock_snapshot: Any,
                                           provider: ExternalMonotonicProvider,
                                           fresh_mission_state_blob_sha: str) -> ClockEpochRootState:
    signer_trust = SignerTrustSnapshot.verify(signer_root.trust_snapshot)
    clock = ClockEpochTrustSnapshot.verify(clock_snapshot, signer_root.trust_snapshot)
    if clock.previous_clock_epoch_sha256 != ZERO_HASH:
        raise ClockEpochRecoveryGuardError("initial clock epoch must use zero predecessor")
    fresh_blob = _git_blob(fresh_mission_state_blob_sha)
    binding = _external_binding(
        provider,
        installation_id=signer_root.installation_id,
        runtime_id=signer_root.runtime_id,
        local_domain=signer_root.local_durability_domain_id,
    )
    previous = _receipt(signer_root.provider_receipt)
    if provider.read_floor() != previous.sequence:
        raise ClockEpochRecoveryGuardError("signer trust root is not current monotonic head")
    snapshot_map = dict(clock_snapshot)
    snapshot_sha = _hash(snapshot_map)
    payload_hash = _hash({
        "schema_version": SCHEMA,
        "purpose": "CLOCK_EPOCH_TRUST_ROOT_BOOTSTRAP",
        "mission_id": MISSION_ID,
        "step_id": PINNED_STEP_ID,
        "signer_trust_snapshot_id": signer_trust.snapshot_id,
        "clock_snapshot_sha256": snapshot_sha,
        "fresh_mission_state_blob_sha": fresh_blob,
        "stale_pressure_carryover_allowed": False,
        "recovery_counts_as_experience": False,
    })
    receipt = provider.issue(
        expected_previous_sequence=previous.sequence,
        previous_receipt_hash=previous.receipt_hash,
        payload_hash=payload_hash,
    )
    verify_monotonic_receipt(
        provider,
        receipt,
        expected_binding=binding,
        expected_previous_sequence=previous.sequence,
        expected_previous_receipt_hash=previous.receipt_hash,
        expected_payload_hash=payload_hash,
    )
    return ClockEpochRootState(
        snapshot_map, snapshot_sha, dict(signer_root.trust_snapshot), payload_hash, receipt,
        fresh_blob, signer_root.installation_id, signer_root.runtime_id,
        signer_root.local_durability_domain_id, "CLOCK_EPOCH_ACTIVE_SHADOW",
    )


def recover_clock_epoch(*, current_root: ClockEpochRootState,
                        replacement_clock_snapshot: Any,
                        provider: ExternalMonotonicProvider,
                        fresh_mission_state_blob_sha: str) -> ClockEpochRootState:
    current = _verify_root(current_root, provider)
    replacement = ClockEpochTrustSnapshot.verify(replacement_clock_snapshot, current_root.signer_trust_snapshot)
    fresh_blob = _git_blob(fresh_mission_state_blob_sha)
    if fresh_blob != current_root.fresh_mission_state_blob_sha:
        raise ClockEpochRecoveryGuardError("fresh Mission authority changed during clock recovery")
    if replacement.previous_clock_epoch_sha256 != current_root.clock_snapshot_sha256:
        raise ClockEpochRecoveryGuardError("CLOCK_EPOCH_PREDECESSOR_MISMATCH")
    if replacement.clock_epoch_id == current.clock_epoch_id:
        raise ClockEpochRecoveryGuardError("CLOCK_EPOCH_DID_NOT_ROTATE")
    if current.clock_epoch_id not in replacement.revoked_clock_epochs:
        raise ClockEpochRecoveryGuardError("OLD_CLOCK_EPOCH_NOT_REVOKED")
    snapshot_map = dict(replacement_clock_snapshot)
    snapshot_sha = _hash(snapshot_map)
    previous = _receipt(current_root.provider_receipt)
    binding = _external_binding(
        provider,
        installation_id=current_root.installation_id,
        runtime_id=current_root.runtime_id,
        local_domain=current_root.local_durability_domain_id,
    )
    payload_hash = _hash({
        "schema_version": SCHEMA,
        "purpose": "AUTHENTICATED_RUNTIME_CLOCK_EPOCH_RECOVERY",
        "mission_id": MISSION_ID,
        "step_id": PINNED_STEP_ID,
        "previous_clock_snapshot_sha256": current_root.clock_snapshot_sha256,
        "replacement_clock_snapshot_sha256": snapshot_sha,
        "fresh_mission_state_blob_sha": fresh_blob,
        "stale_pressure_carryover_allowed": False,
        "terminal_hold_carryover_allowed": False,
        "recovery_counts_as_experience": False,
    })
    receipt = provider.issue(
        expected_previous_sequence=previous.sequence,
        previous_receipt_hash=previous.receipt_hash,
        payload_hash=payload_hash,
    )
    verify_monotonic_receipt(
        provider,
        receipt,
        expected_binding=binding,
        expected_previous_sequence=previous.sequence,
        expected_previous_receipt_hash=previous.receipt_hash,
        expected_payload_hash=payload_hash,
    )
    return ClockEpochRootState(
        snapshot_map, snapshot_sha, dict(current_root.signer_trust_snapshot), payload_hash, receipt,
        fresh_blob, current_root.installation_id, current_root.runtime_id,
        current_root.local_durability_domain_id,
        "CLOCK_EPOCH_RECOVERED_AWAITING_FRESH_AUTHORITY_AND_CLOCK",
        secretary_level="UNKNOWN",
        stale_pressure_carryover_allowed=False,
        terminal_hold_carryover_allowed=False,
        live_routing_authority_allowed=False,
        formal_mutation_allowed=False,
        experience_delta=0,
        operational_progress_delta=0,
    )


def _epoch_genesis(clock_root: ClockEpochRootState) -> str:
    return _hash({
        "purpose": "CLOCK_EPOCH_GENESIS",
        "clock_snapshot_sha256": clock_root.clock_snapshot_sha256,
        "provider_receipt_hash": _receipt(clock_root.provider_receipt).receipt_hash,
    })


@dataclass(frozen=True)
class EpochClockCheckpoint:
    clock_epoch_id: str
    last_clock_seq: int
    last_clock_hash: str
    installation_id: str
    runtime_id: str
    nonce: str
    mac_sha256: str
    schema_version: str = CLOCK_CHECKPOINT_SCHEMA

    def unsigned(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("mac_sha256")
        return d


@dataclass(frozen=True)
class EpochRuntimeClockReceipt:
    clock_epoch_id: str
    clock_seq: int
    previous_clock_hash: str
    installation_id: str
    runtime_id: str
    nonce: str
    mac_sha256: str
    schema_version: str = CLOCK_RECEIPT_SCHEMA

    def unsigned(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("mac_sha256")
        return d

    def receipt_hash(self) -> str:
        return hashlib.sha256(_canon(asdict(self))).hexdigest()


def _clock_secret(root: ClockEpochRootState) -> bytes:
    clock = ClockEpochTrustSnapshot.verify(root.clock_snapshot, root.signer_trust_snapshot)
    return _clock_key(clock.clock_epoch_id)


def sign_epoch_checkpoint(*, clock_root: ClockEpochRootState, last_clock_seq: int,
                          last_clock_hash: str, nonce: str) -> EpochClockCheckpoint:
    if isinstance(last_clock_seq, bool) or not isinstance(last_clock_seq, int) or last_clock_seq < 0:
        raise ClockEpochRecoveryGuardError("last_clock_seq must be nonnegative integer")
    last_hash = _sha256(last_clock_hash, name="last_clock_hash")
    clock = ClockEpochTrustSnapshot.verify(clock_root.clock_snapshot, clock_root.signer_trust_snapshot)
    payload = {
        "clock_epoch_id": clock.clock_epoch_id,
        "last_clock_seq": last_clock_seq,
        "last_clock_hash": last_hash,
        "installation_id": clock_root.installation_id,
        "runtime_id": clock_root.runtime_id,
        "nonce": _token(nonce, name="nonce"),
        "schema_version": CLOCK_CHECKPOINT_SCHEMA,
    }
    mac = hmac.new(_clock_secret(clock_root), _canon(payload), hashlib.sha256).hexdigest()
    return EpochClockCheckpoint(**payload, mac_sha256=mac)


def initial_epoch_checkpoint(clock_root: ClockEpochRootState, *, nonce: str = "epoch-genesis") -> EpochClockCheckpoint:
    return sign_epoch_checkpoint(
        clock_root=clock_root,
        last_clock_seq=0,
        last_clock_hash=_epoch_genesis(clock_root),
        nonce=nonce,
    )


def verify_epoch_checkpoint(value: Any, *, clock_root: ClockEpochRootState,
                            provider: ExternalMonotonicProvider) -> EpochClockCheckpoint:
    clock = _verify_root(clock_root, provider)
    if isinstance(value, EpochClockCheckpoint):
        cp = value
    elif isinstance(value, Mapping):
        try:
            cp = EpochClockCheckpoint(**dict(value))
        except TypeError as exc:
            raise ClockEpochRecoveryGuardError("malformed epoch clock checkpoint") from exc
    else:
        raise ClockEpochRecoveryGuardError("epoch clock checkpoint required")
    if cp.schema_version != CLOCK_CHECKPOINT_SCHEMA or cp.clock_epoch_id != clock.clock_epoch_id:
        raise ClockEpochRecoveryGuardError("clock checkpoint epoch/schema mismatch")
    if cp.installation_id != clock_root.installation_id or cp.runtime_id != clock_root.runtime_id:
        raise ClockEpochRecoveryGuardError("clock checkpoint runtime scope mismatch")
    if isinstance(cp.last_clock_seq, bool) or not isinstance(cp.last_clock_seq, int) or cp.last_clock_seq < 0:
        raise ClockEpochRecoveryGuardError("invalid checkpoint sequence")
    _sha256(cp.last_clock_hash, name="last_clock_hash")
    expected = hmac.new(_clock_secret(clock_root), _canon(cp.unsigned()), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, cp.mac_sha256):
        raise ClockEpochRecoveryGuardError("clock checkpoint authentication failed")
    return cp


def sign_epoch_clock(*, clock_root: ClockEpochRootState, checkpoint: Any,
                     provider: ExternalMonotonicProvider, clock_seq: int,
                     nonce: str) -> EpochRuntimeClockReceipt:
    cp = verify_epoch_checkpoint(checkpoint, clock_root=clock_root, provider=provider)
    if isinstance(clock_seq, bool) or not isinstance(clock_seq, int) or clock_seq <= cp.last_clock_seq:
        raise ClockEpochRecoveryGuardError("runtime clock replay/non-monotonic sequence")
    payload = {
        "clock_epoch_id": cp.clock_epoch_id,
        "clock_seq": clock_seq,
        "previous_clock_hash": cp.last_clock_hash,
        "installation_id": cp.installation_id,
        "runtime_id": cp.runtime_id,
        "nonce": _token(nonce, name="nonce"),
        "schema_version": CLOCK_RECEIPT_SCHEMA,
    }
    mac = hmac.new(_clock_secret(clock_root), _canon(payload), hashlib.sha256).hexdigest()
    return EpochRuntimeClockReceipt(**payload, mac_sha256=mac)


def verify_epoch_clock(value: Any, *, checkpoint: Any, clock_root: ClockEpochRootState,
                       provider: ExternalMonotonicProvider) -> EpochRuntimeClockReceipt:
    cp = verify_epoch_checkpoint(checkpoint, clock_root=clock_root, provider=provider)
    if isinstance(value, EpochRuntimeClockReceipt):
        receipt = value
    elif isinstance(value, Mapping):
        try:
            receipt = EpochRuntimeClockReceipt(**dict(value))
        except TypeError as exc:
            raise ClockEpochRecoveryGuardError("malformed epoch runtime clock receipt") from exc
    else:
        raise ClockEpochRecoveryGuardError("epoch runtime clock receipt required")
    if receipt.schema_version != CLOCK_RECEIPT_SCHEMA or receipt.clock_epoch_id != cp.clock_epoch_id:
        raise ClockEpochRecoveryGuardError("runtime clock epoch/schema mismatch")
    if receipt.installation_id != cp.installation_id or receipt.runtime_id != cp.runtime_id:
        raise ClockEpochRecoveryGuardError("runtime clock scope mismatch")
    if receipt.previous_clock_hash != cp.last_clock_hash or receipt.clock_seq <= cp.last_clock_seq:
        raise ClockEpochRecoveryGuardError("runtime clock predecessor/replay mismatch")
    expected = hmac.new(_clock_secret(clock_root), _canon(receipt.unsigned()), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, receipt.mac_sha256):
        raise ClockEpochRecoveryGuardError("runtime clock authentication failed")
    return receipt


def advance_epoch_checkpoint(*, clock_root: ClockEpochRootState, checkpoint: Any,
                             clock_receipt: Any, provider: ExternalMonotonicProvider,
                             nonce: str) -> EpochClockCheckpoint:
    receipt = verify_epoch_clock(
        clock_receipt, checkpoint=checkpoint, clock_root=clock_root, provider=provider,
    )
    return sign_epoch_checkpoint(
        clock_root=clock_root,
        last_clock_seq=receipt.clock_seq,
        last_clock_hash=receipt.receipt_hash(),
        nonce=nonce,
    )


@dataclass(frozen=True)
class RecoveryGate:
    state: str
    selected_state: str
    guard_status: str
    return_condition: str
    clock_epoch_id: str
    secretary_level: str
    pressure_inputs: Mapping[str, float]
    pressure_history_consumed: bool = False
    stale_pressure_carryover_allowed: bool = False
    terminal_hold_carryover_allowed: bool = False
    live_routing_authority_allowed: bool = False
    formal_mutation_allowed: bool = False
    experience_delta: int = 0
    operational_progress_delta: int = 0


def open_recovery_gate(*, clock_root: ClockEpochRootState,
                       provider: ExternalMonotonicProvider,
                       signed_authority: Any) -> RecoveryGate:
    clock = _verify_root(clock_root, provider)
    if clock_root.state != "CLOCK_EPOCH_RECOVERED_AWAITING_FRESH_AUTHORITY_AND_CLOCK":
        raise ClockEpochRecoveryGuardError("clock root is not awaiting recovery re-entry")
    try:
        authority = verify_signed_authority(signed_authority, clock_root.signer_trust_snapshot)
    except GearboxGuardError as exc:
        raise ClockEpochRecoveryGuardError(str(exc)) from exc
    if authority.mission_state_blob_sha.lower() != clock_root.fresh_mission_state_blob_sha:
        raise ClockEpochRecoveryGuardError("fresh authority does not bind current Mission blob")
    return RecoveryGate(
        state="CLOCK_RECOVERY_FRESH_AUTHORITY_READY_SHADOW",
        selected_state=authority.selected_state,
        guard_status=authority.guard_status,
        return_condition=authority.return_condition,
        clock_epoch_id=clock.clock_epoch_id,
        secretary_level="UNKNOWN",
        pressure_inputs=dict(NEUTRAL_PRESSURE),
    )


@dataclass(frozen=True)
class EpochBoundSecretaryObservation:
    signal_fingerprint: str
    signal_id: str
    clock_epoch_id: str
    installation_id: str
    runtime_id: str
    mac_sha256: str
    signer_id: str = SECRETARY_SIGNER_ID
    mission_id: str = MISSION_ID
    step_id: int = PINNED_STEP_ID
    schema_version: str = EPOCH_OBSERVATION_SCHEMA

    def unsigned(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("mac_sha256")
        return d


def sign_epoch_bound_secretary_observation(envelope_value: Any, *, clock_root: ClockEpochRootState,
                                            secretary_secret: bytes) -> EpochBoundSecretaryObservation:
    secret = _validate_secret(secretary_secret, expected_hash=SECRETARY_KEY_SHA256, name="secretary_secret")
    env = SecretarySignalEnvelope.from_value(envelope_value)
    clock = ClockEpochTrustSnapshot.verify(clock_root.clock_snapshot, clock_root.signer_trust_snapshot)
    if env.installation_id != clock_root.installation_id or env.runtime_id != clock_root.runtime_id:
        raise ClockEpochRecoveryGuardError("secretary envelope runtime scope mismatch")
    payload = {
        "signal_fingerprint": env.canonical_fingerprint(),
        "signal_id": env.signal_id,
        "clock_epoch_id": clock.clock_epoch_id,
        "installation_id": env.installation_id,
        "runtime_id": env.runtime_id,
        "signer_id": SECRETARY_SIGNER_ID,
        "mission_id": MISSION_ID,
        "step_id": PINNED_STEP_ID,
        "schema_version": EPOCH_OBSERVATION_SCHEMA,
    }
    mac = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return EpochBoundSecretaryObservation(**payload, mac_sha256=mac)


def _verify_epoch_observation(value: Any, envelope: SecretarySignalEnvelope, *,
                              clock_root: ClockEpochRootState,
                              secretary_secret: bytes) -> EpochBoundSecretaryObservation:
    secret = _validate_secret(secretary_secret, expected_hash=SECRETARY_KEY_SHA256, name="secretary_secret")
    if isinstance(value, EpochBoundSecretaryObservation):
        obs = value
    elif isinstance(value, Mapping):
        try:
            obs = EpochBoundSecretaryObservation(**dict(value))
        except TypeError as exc:
            raise ClockEpochRecoveryGuardError("malformed epoch-bound secretary observation") from exc
    else:
        raise ClockEpochRecoveryGuardError("epoch-bound secretary observation required")
    clock = ClockEpochTrustSnapshot.verify(clock_root.clock_snapshot, clock_root.signer_trust_snapshot)
    if obs.schema_version != EPOCH_OBSERVATION_SCHEMA or obs.mission_id != MISSION_ID or obs.step_id != PINNED_STEP_ID:
        raise ClockEpochRecoveryGuardError("secretary observation scope/schema mismatch")
    if obs.clock_epoch_id != clock.clock_epoch_id:
        raise ClockEpochRecoveryGuardError("stale secretary observation from previous clock epoch")
    if obs.signal_id != envelope.signal_id or obs.signal_fingerprint != envelope.canonical_fingerprint():
        raise ClockEpochRecoveryGuardError("secretary observation binding mismatch")
    if obs.installation_id != envelope.installation_id or obs.runtime_id != envelope.runtime_id:
        raise ClockEpochRecoveryGuardError("secretary observation runtime scope mismatch")
    expected = hmac.new(secret, _canonical_bytes(obs.unsigned()), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, obs.mac_sha256):
        raise ClockEpochRecoveryGuardError("secretary observation authentication failed")
    return obs


def project_fresh_secretary_after_recovery(*, gate: RecoveryGate,
                                           clock_root: ClockEpochRootState,
                                           provider: ExternalMonotonicProvider,
                                           envelope_value: Any,
                                           epoch_observation: Any,
                                           checkpoint: Any,
                                           clock_receipt: Any,
                                           secretary_secret: bytes,
                                           authority_conflict: bool = False) -> SecretarySignalProjection:
    if gate.state != "CLOCK_RECOVERY_FRESH_AUTHORITY_READY_SHADOW" or gate.clock_epoch_id != ClockEpochTrustSnapshot.verify(clock_root.clock_snapshot, clock_root.signer_trust_snapshot).clock_epoch_id:
        raise ClockEpochRecoveryGuardError("fresh recovery gate required")
    if type(authority_conflict) is not bool:
        raise ClockEpochRecoveryGuardError("authority_conflict must be bool")
    clock = verify_epoch_clock(
        clock_receipt, checkpoint=checkpoint, clock_root=clock_root, provider=provider,
    )
    env = SecretarySignalEnvelope.from_value(envelope_value)
    _verify_epoch_observation(
        epoch_observation, env, clock_root=clock_root, secretary_secret=secretary_secret,
    )
    fingerprint = env.canonical_fingerprint()
    if authority_conflict:
        return neutral_secretary_projection(
            status="AUTHORITY_CONFLICT_ZERO_EFFECT_POST_CLOCK_RECOVERY",
            signal_id=env.signal_id, fingerprint=fingerprint,
            dropped_fields=tuple(sorted(env.measurements.keys())),
        )
    if clock.clock_seq < env.issued_seq:
        return neutral_secretary_projection(
            status="FUTURE_ENVELOPE_ZERO_EFFECT_POST_CLOCK_RECOVERY",
            signal_id=env.signal_id, fingerprint=fingerprint,
            dropped_fields=tuple(sorted(env.measurements.keys())),
        )
    if clock.clock_seq > env.valid_through_seq:
        return neutral_secretary_projection(
            status="STALE_ENVELOPE_ZERO_EFFECT_POST_CLOCK_RECOVERY",
            signal_id=env.signal_id, fingerprint=fingerprint,
            dropped_fields=tuple(sorted(env.measurements.keys())),
        )
    observed = dict(NEUTRAL_PRESSURE)
    accepted: list[str] = []
    dropped: list[str] = []
    for field_name in sorted(NEUTRAL_PRESSURE):
        measurement = env.measurements.get(field_name)
        if measurement is None:
            dropped.append(field_name)
        elif measurement.observed_seq <= clock.clock_seq <= measurement.valid_through_seq:
            observed[field_name] = measurement.value
            accepted.append(field_name)
        else:
            dropped.append(field_name)
    if not accepted:
        return neutral_secretary_projection(
            status="NO_FRESH_FIELDS_ZERO_EFFECT_POST_CLOCK_RECOVERY",
            signal_id=env.signal_id, fingerprint=fingerprint,
            dropped_fields=tuple(dropped),
        )
    return SecretarySignalProjection(
        signal_id=env.signal_id,
        envelope_fingerprint=fingerprint,
        observed_secretary_level=env.secretary_level,
        observed_pressure_inputs=observed,
        routing_secretary_level=env.secretary_level,
        routing_pressure_inputs=dict(observed),
        accepted_fields=tuple(accepted),
        dropped_fields=tuple(dropped),
        status="FRESH_CURRENT_EPOCH_SECRETARY_ROUTING_SHADOW",
        routing_authority_allowed=True,
        formal_mutation_allowed=False,
        verified_experience_delta=0,
        operational_progress_delta=0,
    )


def recovery_dataflow_boundaries() -> dict[str, object]:
    return {
        "formal_mutation_allowed": False,
        "live_routing_authority_allowed": False,
        "recovery_counts_as_experience": False,
        "recovery_counts_as_operational_progress": False,
        "pressure_history_consumed": False,
        "stale_pressure_carryover_allowed": False,
        "terminal_hold_carryover_allowed": False,
        "secretary_clock_metadata_counts_as_experience": False,
        "secretary_clock_metadata_counts_as_personality": False,
        "secretary_clock_metadata_counts_as_appraisal_reward": False,
        "secretary_clock_metadata_counts_as_trauma_or_relief": False,
        "p_base_mutation_allowed": False,
        "real_external_provider_installed": False,
        "production_clock_key_protection_proven": False,
        "production_secretary_key_protection_proven": False,
    }
