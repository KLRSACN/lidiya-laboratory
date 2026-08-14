from __future__ import annotations
import argparse, hashlib, json, os, tempfile
from pathlib import Path
from typing import Any, Dict
from evidence_reconciler import AUTH_REF, ReconcileError, load_installation_metadata, verify_real_local_candidate

FORBIDDEN_KEYS={"raw_chat","conversation","messages","hidden_state","system_prompt","secret","secrets","token","tokens","password","passwords","credential","credentials"}
class BundleError(ValueError): pass

def canonical_json(value: Any) -> str:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))

def _contains_forbidden(value: Any) -> bool:
    if isinstance(value,dict):
        for k,v in value.items():
            key=str(k).lower()
            if key in FORBIDDEN_KEYS or any(x in key for x in ("password","credential","secret","token")):
                return True
            if _contains_forbidden(v): return True
    elif isinstance(value,list):
        return any(_contains_forbidden(v) for v in value)
    return False

def _read_json(path: Path) -> tuple[Dict[str,Any],bytes]:
    if not path.is_file(): raise BundleError(f"missing evidence file: {path.name}")
    raw=path.read_bytes()
    try: data=json.loads(raw.decode("utf-8-sig"))
    except Exception as exc: raise BundleError(f"invalid json: {path.name}") from exc
    if not isinstance(data,dict): raise BundleError("evidence json must be object")
    if _contains_forbidden(data): raise BundleError("forbidden raw-context or secret-like field")
    return data,raw

def build_local_evidence_bundle(workspace_root: str|Path, *, write: bool=True) -> Dict[str,Any]:
    root=Path(workspace_root).resolve(strict=False)
    lidiya=(root/".lidiya").resolve(strict=False)
    try:
        if os.path.commonpath([str(root),str(lidiya)]) != str(root): raise BundleError(".lidiya outside workspace")
    except ValueError as exc: raise BundleError("workspace containment failure") from exc
    install_path=lidiya/"installation.json"; canary_path=lidiya/"local_canary_evidence.json"
    install,install_raw=_read_json(install_path); canary,canary_raw=_read_json(canary_path)
    try:
        verified=verify_real_local_candidate(canary,install,workspace_root=root,online_source_attested=False)
    except ReconcileError as exc: raise BundleError(str(exc)) from exc
    bundle={
        "schema_version":"1.0","mission_id":"LCR-EVOLUTION-0005","authorization_ref":AUTH_REF,
        "status":"REAL_LOCAL_EVIDENCE_BUNDLE_CANDIDATE_UNATTESTED","installation_id":install["installation_id"],
        "installation_fingerprint":verified["installation_fingerprint"],"canary_sha256":verified["canary_sha256"],
        "source_files":{
            ".lidiya/installation.json":{"sha256":sha256_bytes(install_raw)},
            ".lidiya/local_canary_evidence.json":{"sha256":sha256_bytes(canary_raw)}
        },
        "reconciliation":verified,"online_source_attested":False,"E3_promoted":False,
        "contains_raw_chat":False,"contains_secret_material":False
    }
    bundle["bundle_sha256"]=sha256_json(bundle)
    if write:
        outdir=lidiya/"outbox"; outdir.mkdir(parents=True,exist_ok=True); target=outdir/"local_evidence_bundle.json"
        payload=(json.dumps(bundle,sort_keys=True,indent=2,ensure_ascii=False)+"\n").encode("utf-8")
        fd,tmp=tempfile.mkstemp(prefix=target.name+".",dir=str(outdir))
        try:
            with os.fdopen(fd,"wb") as f: f.write(payload); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    return bundle

def verify_bundle(bundle: Dict[str,Any]) -> bool:
    if not isinstance(bundle,dict): raise BundleError("bundle must be object")
    if bundle.get("status")!="REAL_LOCAL_EVIDENCE_BUNDLE_CANDIDATE_UNATTESTED": raise BundleError("invalid status")
    if bundle.get("authorization_ref")!=AUTH_REF or bundle.get("mission_id")!="LCR-EVOLUTION-0005": raise BundleError("authority mismatch")
    if bundle.get("online_source_attested") is not False or bundle.get("E3_promoted") is not False: raise BundleError("premature attestation/promotion")
    if bundle.get("contains_raw_chat") is not False or bundle.get("contains_secret_material") is not False: raise BundleError("unsafe bundle marker")
    claimed=bundle.get("bundle_sha256"); body={k:v for k,v in bundle.items() if k!="bundle_sha256"}
    if not isinstance(claimed,str) or claimed!=sha256_json(body): raise BundleError("bundle hash mismatch")
    return True

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--workspace-root",required=True); ns=ap.parse_args(); print(json.dumps(build_local_evidence_bundle(ns.workspace_root),ensure_ascii=False))
if __name__=="__main__": main()
