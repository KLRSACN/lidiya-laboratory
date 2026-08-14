from __future__ import annotations
import hashlib, json
from pathlib import Path

AUTH_REF = "authorizations/LCR-EVOLUTION-0005-LOCAL-COMMAND-TOWER-24H-ADDENDUM-20260814.json"
FIXED_COMMAND_ID = "LOCAL-CANARY-ECHO-001"
FIXED_STDOUT = "LIDIYA_CANARY"

class ReconcileError(ValueError):
    pass

def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def load_installation_metadata(workspace_root):
    path = Path(workspace_root).resolve(strict=False) / ".lidiya" / "installation.json"
    if not path.is_file():
        raise ReconcileError("missing installation metadata")
    data = json.loads(path.read_text(encoding="utf-8"))
    installation_id = str(data.get("installation_id", "")).strip()
    if not installation_id:
        raise ReconcileError("missing installation_id")
    if data.get("secrets_present") not in (False, None):
        raise ReconcileError("installation metadata may not contain secrets")
    return data

def verify_real_local_candidate(evidence, installation_metadata):
    if evidence.get("mode") != "WINDOWS_FIXED_HARMLESS_ECHO":
        raise ReconcileError("wrong mode")
    iid = str(installation_metadata.get("installation_id", ""))
    if not iid or evidence.get("installation_id") != iid:
        raise ReconcileError("installation_id mismatch")
    if evidence.get("authorization_ref") != AUTH_REF:
        raise ReconcileError("wrong authorization")
    if evidence.get("command_id") != FIXED_COMMAND_ID:
        raise ReconcileError("wrong fixed command")
    if evidence.get("arbitrary_command_input") is not False:
        raise ReconcileError("arbitrary command flag")
    if int(evidence.get("exit_code", -1)) != 0:
        raise ReconcileError("nonzero exit")
    if str(evidence.get("stdout", "")).strip() != FIXED_STDOUT:
        raise ReconcileError("wrong fixed output")
    claimed = evidence.get("canary_sha256")
    body = {k: v for k, v in evidence.items() if k != "canary_sha256"}
    if not claimed or claimed != sha256_json(body):
        raise ReconcileError("canary hash mismatch")
    for key in ("command_id", "stdout", "stderr", "exit_code", "evidence_sha256", "authorization_ref", "installation_id", "provenance"):
        if key not in evidence:
            raise ReconcileError("missing provenance/evidence field: " + key)
    prov = evidence["provenance"]
    if prov.get("source") != "LOCAL_OWNER_WINDOWS_EXECUTION" or prov.get("observed_by") != "LOCAL_CANARY":
        raise ReconcileError("invalid provenance")
    return {
        "status": "E3_CANDIDATE_REAL_LOCAL_EVIDENCE_PENDING_ONLINE_SOURCE_ATTESTATION",
        "installation_id": iid,
        "canary_sha256": claimed,
        "authorization_ref": AUTH_REF,
        "owner_machine_claimed_by_reconciler": False,
    }
