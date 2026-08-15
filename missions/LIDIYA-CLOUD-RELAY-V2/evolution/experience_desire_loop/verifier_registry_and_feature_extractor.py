from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

def canonical_hash(payload: object) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode()).hexdigest()

@dataclass(frozen=True)
class VerifierRecord:
    verifier_id: str
    generation: int
    method_family: str
    policy_hash: str
    active: bool = True
    def key(self) -> str:
        return f"{self.verifier_id}:{self.generation}"

class VerifierRegistry:
    def __init__(self, records: Sequence[VerifierRecord]):
        self._records = {}
        for record in records:
            if not record.verifier_id or not record.method_family or not record.policy_hash:
                raise ValueError("INVALID_VERIFIER_RECORD")
            if record.key() in self._records:
                raise ValueError("DUPLICATE_VERIFIER_IDENTITY")
            self._records[record.key()] = record
    def registry_hash(self) -> str:
        return canonical_hash({"verifiers":[r.__dict__ for r in sorted(self._records.values(), key=lambda x:x.key())]})
    def accept_attestation(self, *, source_actor_id: str, attestation: Mapping[str, object]) -> bool:
        key=f"{attestation.get('verifier_id','')}:{attestation.get('verifier_generation','')}"
        record=self._records.get(key)
        if record is None or not record.active: return False
        if attestation.get("verdict") != "PASS": return False
        if attestation.get("verifier_id") == source_actor_id: return False
        if attestation.get("independent_of_source") is not True: return False
        if attestation.get("method_family") != record.method_family: return False
        if attestation.get("verification_policy_hash") != record.policy_hash: return False
        return True

class DeterministicFeatureExtractor:
    """Shadow-only feature extraction. Thresholds/coefficients remain TEST_REQUIRED."""
    FORBIDDEN_FIELDS={"trust","trust_score","verified","verification","alignment","authority","personality_write"}
    SCHEMA_VERSION="EDL-FEATURES-V0.1-TEST_REQUIRED"
    @classmethod
    def extract(cls, observation: Mapping[str, object]) -> dict[str,float]:
        for field in cls.FORBIDDEN_FIELDS:
            if field in observation:
                raise ValueError(f"RAW_EVENT_SELF_ASSERTION_FORBIDDEN:{field}")
        text=str(observation.get("text",""))
        magnitude=float(observation.get("magnitude",0.0))
        novelty=float(observation.get("novelty",0.0))
        risk=float(observation.get("risk",0.0))
        valence=float(observation.get("valence",0.0))
        clip11=lambda v:max(-1.0,min(1.0,v))
        clip01=lambda v:max(0.0,min(1.0,v))
        return {"magnitude":clip01(magnitude),"novelty":clip01(novelty),"risk":clip01(risk),"valence":clip11(valence),"text_presence":1.0 if text.strip() else 0.0}
