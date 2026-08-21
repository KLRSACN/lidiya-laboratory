from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from gearbox_controller import GearboxGuardError
from gearbox_authority_projection_shadow_v01 import AuthorityDecisionEnvelope
from gearbox_v2_1_repair_shadow_v01 import AcceptedExperienceReceipt, MISSION_ID, canonical_event_id

SCHEMA = "1.0-shadow"
PINNED_STEP_ID = 9
# Synthetic regression identities only. These prove protocol semantics, not protected production keys.
SYNTHETIC_KEYS = {
    "LCR-A": {"a-epoch-1": b"shadow-lcr-a-regression-key-v1"},
    "LCR-C": {"c-epoch-1": b"shadow-lcr-c-regression-key-v1"},
    "INDEPENDENT_VERIFIER": {"iv-epoch-1": b"shadow-independent-verifier-key-v1"},
}


def _canon(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _mac(key: bytes, payload: Mapping[str, Any]) -> str:
    return hmac.new(key, _canon(payload), hashlib.sha256).hexdigest()


def _key(role: str, epoch: str) -> bytes:
    try:
        return SYNTHETIC_KEYS[role][epoch]
    except KeyError as exc:
        raise GearboxGuardError("unknown signer role/key epoch") from exc


@dataclass(frozen=True)
class SignerTrustSnapshot:
    schema_version: str
    mission_id: str
    step_id: int
    snapshot_id: str
    authority_active_epoch: str
    verifier_active_epochs: Mapping[str, str]
    revoked_epochs: tuple[str, ...]
    previous_snapshot_sha256: str
    signature: str

    def unsigned(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("signature")
        d["verifier_active_epochs"] = dict(sorted(self.verifier_active_epochs.items()))
        d["revoked_epochs"] = list(self.revoked_epochs)
        return d

    @classmethod
    def verify(cls, value: Any) -> "SignerTrustSnapshot":
        if not isinstance(value, Mapping):
            raise GearboxGuardError("SignerTrustSnapshot required")
        try:
            s = cls(**dict(value))
        except TypeError as exc:
            raise GearboxGuardError("malformed SignerTrustSnapshot") from exc
        if s.schema_version != SCHEMA or s.mission_id != MISSION_ID or s.step_id != PINNED_STEP_ID:
            raise GearboxGuardError("signer trust snapshot scope mismatch")
        canonical_event_id(s.snapshot_id)
        if s.authority_active_epoch in s.revoked_epochs:
            raise GearboxGuardError("active authority epoch is revoked")
        _key("LCR-A", s.authority_active_epoch)
        for role, epoch in s.verifier_active_epochs.items():
            if role not in {"LCR-C", "INDEPENDENT_VERIFIER"} or epoch in s.revoked_epochs:
                raise GearboxGuardError("invalid or revoked verifier epoch")
            _key(role, epoch)
        if not hmac.compare_digest(s.signature, _mac(_key("LCR-A", s.authority_active_epoch), s.unsigned())):
            raise GearboxGuardError("invalid signer trust snapshot signature")
        return s


@dataclass(frozen=True)
class SignedAuthorityDecision:
    envelope: Mapping[str, Any]
    signer_role: str
    key_epoch: str
    trust_snapshot_id: str
    signature: str

    def unsigned(self) -> dict[str, Any]:
        return {"envelope": dict(self.envelope), "signer_role": self.signer_role, "key_epoch": self.key_epoch, "trust_snapshot_id": self.trust_snapshot_id}


@dataclass(frozen=True)
class SignedAcceptedExperience:
    receipt: Mapping[str, Any]
    signer_role: str
    key_epoch: str
    trust_snapshot_id: str
    signature: str

    def unsigned(self) -> dict[str, Any]:
        return {"receipt": dict(self.receipt), "signer_role": self.signer_role, "key_epoch": self.key_epoch, "trust_snapshot_id": self.trust_snapshot_id}


def verify_signed_authority(value: Any, trust_value: Any) -> AuthorityDecisionEnvelope:
    trust = SignerTrustSnapshot.verify(trust_value)
    if not isinstance(value, Mapping):
        raise GearboxGuardError("SignedAuthorityDecision required")
    try:
        signed = SignedAuthorityDecision(**dict(value))
    except TypeError as exc:
        raise GearboxGuardError("malformed SignedAuthorityDecision") from exc
    if signed.signer_role != "LCR-A" or signed.key_epoch != trust.authority_active_epoch:
        raise GearboxGuardError("authority signer is not current trusted epoch")
    if signed.key_epoch in trust.revoked_epochs or signed.trust_snapshot_id != trust.snapshot_id:
        raise GearboxGuardError("authority signer revoked or trust snapshot mismatch")
    if not hmac.compare_digest(signed.signature, _mac(_key("LCR-A", signed.key_epoch), signed.unsigned())):
        raise GearboxGuardError("invalid authority signature")
    return AuthorityDecisionEnvelope.from_value(signed.envelope)


def verify_signed_experience(value: Any, trust_value: Any) -> AcceptedExperienceReceipt:
    trust = SignerTrustSnapshot.verify(trust_value)
    if not isinstance(value, Mapping):
        raise GearboxGuardError("SignedAcceptedExperience required")
    try:
        signed = SignedAcceptedExperience(**dict(value))
    except TypeError as exc:
        raise GearboxGuardError("malformed SignedAcceptedExperience") from exc
    expected_epoch = trust.verifier_active_epochs.get(signed.signer_role)
    if expected_epoch is None or signed.key_epoch != expected_epoch:
        raise GearboxGuardError("experience signer is not current trusted verifier epoch")
    if signed.key_epoch in trust.revoked_epochs or signed.trust_snapshot_id != trust.snapshot_id:
        raise GearboxGuardError("experience signer revoked or trust snapshot mismatch")
    if not hmac.compare_digest(signed.signature, _mac(_key(signed.signer_role, signed.key_epoch), signed.unsigned())):
        raise GearboxGuardError("invalid experience signature")
    receipt = AcceptedExperienceReceipt.from_value(signed.receipt)
    if receipt is None or receipt.verifier_role != signed.signer_role or receipt.step_id != PINNED_STEP_ID:
        raise GearboxGuardError("experience receipt binding mismatch")
    return receipt


def sign_for_regression(payload: Mapping[str, Any], role: str, epoch: str) -> str:
    """Synthetic test helper only; production signing is explicitly out of scope."""
    return _mac(_key(role, epoch), payload)
