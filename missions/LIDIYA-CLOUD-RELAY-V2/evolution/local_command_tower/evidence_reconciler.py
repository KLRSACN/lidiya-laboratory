from __future__ import annotations
import hashlib, json, uuid
from pathlib import Path
from typing import Any, Dict

AUTH_REF="authorizations/LCR-EVOLUTION-0005-LOCAL-COMMAND-TOWER-24H-ADDENDUM-20260814.json"
FIXED_COMMAND_ID="LOCAL-CANARY-ECHO-001"
FIXED_STDOUT="LIDIYA_CANARY"

class ReconcileError(ValueError): pass

def canonical_json(value: Any) -> str: return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def sha256_json(value: Any) -> str: return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def validate_installation_metadata(data: Dict[str,Any],workspace_root: str|Path|None=None) -> Dict[str,Any]:
    if not isinstance(data,dict) or data.get("schema_version")!="1.0": raise ReconcileError("unsupported installation metadata")
    iid=str(data.get("installation_id","")).strip()
    try: uuid.UUID(iid)
    except Exception as exc: raise ReconcileError("invalid installation_id") from exc
    raw_root=str(data.get("install_root","") or "").strip()
    if not raw_root: raise ReconcileError("missing install_root")
    root=Path(raw_root).resolve(strict=False)
    if workspace_root is not None and root!=Path(workspace_root).resolve(strict=False): raise ReconcileError("install_root mismatch")
    if data.get("privilege")!="USER_SPACE": raise ReconcileError("privilege mismatch")
    if data.get("transport")!="LOOPBACK_AND_WORKSPACE_SPOOL": raise ReconcileError("transport mismatch")
    return dict(data)

def load_installation_metadata(workspace_root):
    root=Path(workspace_root).resolve(strict=False); path=root/".lidiya"/"installation.json"
    if not path.is_file(): raise ReconcileError("missing installation metadata")
    try: data=json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc: raise ReconcileError("invalid installation json") from exc
    return validate_installation_metadata(data,root)

def verify_real_local_candidate(evidence: Dict[str,Any],installation_metadata: Dict[str,Any],*,workspace_root: str|Path|None=None,online_source_attested: bool=False) -> Dict[str,Any]:
    meta=validate_installation_metadata(installation_metadata,workspace_root)
    if not isinstance(evidence,dict): raise ReconcileError("evidence must be object")
    if evidence.get("mode")!="WINDOWS_FIXED_HARMLESS_ECHO": raise ReconcileError("wrong mode")
    iid=meta["installation_id"]
    if evidence.get("installation_id")!=iid: raise ReconcileError("installation_id mismatch")
    if evidence.get("installation_fingerprint")!=sha256_json(meta): raise ReconcileError("installation fingerprint mismatch")
    evidence_root_raw=str(evidence.get("install_root","") or "").strip()
    if not evidence_root_raw: raise ReconcileError("missing evidence install_root")
    expected_root=str(Path(str(meta["install_root"])).resolve(strict=False))
    if str(Path(evidence_root_raw).resolve(strict=False))!=expected_root: raise ReconcileError("evidence install_root mismatch")
    if evidence.get("authorization_ref")!=AUTH_REF: raise ReconcileError("wrong authorization")
    if evidence.get("command_id")!=FIXED_COMMAND_ID: raise ReconcileError("wrong fixed command")
    if evidence.get("arbitrary_command_input") is not False: raise ReconcileError("arbitrary command flag")
    if evidence.get("promotion_status")!="REAL_LOCAL_CANARY_EVIDENCE_CANDIDATE_UNATTESTED": raise ReconcileError("unexpected local promotion status")
    try: exit_code=int(evidence.get("exit_code",-1))
    except Exception as exc: raise ReconcileError("invalid exit code") from exc
    if exit_code!=0: raise ReconcileError("nonzero exit")
    if str(evidence.get("stdout","")).strip()!=FIXED_STDOUT: raise ReconcileError("wrong fixed output")
    if not isinstance(evidence.get("stderr"),str): raise ReconcileError("stderr missing")
    command_hash=evidence.get("evidence_sha256")
    if not isinstance(command_hash,str) or len(command_hash)!=64: raise ReconcileError("invalid command evidence hash")
    claimed=evidence.get("canary_sha256"); body={k:v for k,v in evidence.items() if k!="canary_sha256"}
    if not isinstance(claimed,str) or claimed!=sha256_json(body): raise ReconcileError("canary hash mismatch")
    prov=evidence.get("provenance")
    if not isinstance(prov,dict) or prov.get("source")!="LOCAL_OWNER_WINDOWS_EXECUTION" or prov.get("observed_by")!="LOCAL_CANARY": raise ReconcileError("invalid provenance")
    status="REAL_LOCAL_CANARY_EVIDENCE_ATTESTED_CANDIDATE" if online_source_attested else "REAL_LOCAL_CANARY_EVIDENCE_CANDIDATE_UNATTESTED"
    result={"status":status,"installation_id":iid,"installation_fingerprint":sha256_json(meta),"canary_sha256":claimed,"authorization_ref":AUTH_REF,"online_source_attested":bool(online_source_attested),"E3_promoted":False,"owner_machine_claimed_by_reconciler":False}
    result["reconciliation_sha256"]=sha256_json(result)
    return result
