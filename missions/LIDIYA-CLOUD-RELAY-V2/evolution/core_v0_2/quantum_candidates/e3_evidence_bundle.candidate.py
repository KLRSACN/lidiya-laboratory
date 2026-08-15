from __future__ import annotations
import hashlib, json, re, uuid
from pathlib import Path
from typing import Any, Dict

MISSION_ID="LCR-EVOLUTION-0005"
AUTH_REF="authorizations/LCR-EVOLUTION-0005-LOCAL-COMMAND-TOWER-24H-ADDENDUM-20260814.json"
FIXED_MODE="WINDOWS_FIXED_HARMLESS_ECHO"
FIXED_COMMAND_ID="LOCAL-CANARY-ECHO-001"
FIXED_STDOUT="LIDIYA_CANARY"
PROMOTION="E3_EVIDENCE_READY_FOR_ONLINE_ATTESTATION_CANDIDATE"
REQUIRED_FILES={
 "evolution/small_nest/INSTALL_SMALL_NEST.ps1",
 "evolution/small_nest/START_SMALL_NEST.cmd",
 "evolution/small_nest/CHECK_SMALL_NEST_HEALTH.ps1",
 "evolution/small_nest/RUN_LOCAL_CANARY.cmd",
 "evolution/local_command_tower/local_canary.py",
 "evolution/local_command_tower/evidence_reconciler.py",
}
HEX64=re.compile(r"^[0-9a-f]{64}$")

class E3BundleError(ValueError): pass

def canonical_json(value: Any)->str:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def sha256_json(value: Any)->str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def _root(value: Any)->Path:
    raw=str(value or "").strip()
    if not raw: raise E3BundleError("missing install_root")
    return Path(raw).resolve(strict=False)

def validate_bundle(bundle: Dict[str,Any], *, workspace_root: str|Path|None=None)->Dict[str,Any]:
    if not isinstance(bundle,dict) or bundle.get("schema_version")!="1.0": raise E3BundleError("bad schema")
    if bundle.get("mission_id")!=MISSION_ID: raise E3BundleError("wrong mission")
    if bundle.get("authorization_ref")!=AUTH_REF: raise E3BundleError("wrong authorization")
    if bundle.get("capture_mode")!="OWNER_WINDOWS_LOCAL_PACKAGE": raise E3BundleError("wrong capture mode")
    if bundle.get("promotion_status")!=PROMOTION or bundle.get("E3_promoted") is True: raise E3BundleError("premature promotion")

    inst=bundle.get("installation")
    if not isinstance(inst,dict) or inst.get("schema_version")!="1.0": raise E3BundleError("bad installation")
    try: uuid.UUID(str(inst.get("installation_id","")))
    except Exception as exc: raise E3BundleError("invalid installation_id") from exc
    root=_root(inst.get("install_root"))
    if workspace_root is not None and root!=Path(workspace_root).resolve(strict=False): raise E3BundleError("root mismatch")
    if inst.get("privilege")!="USER_SPACE" or inst.get("transport")!="LOOPBACK_AND_WORKSPACE_SPOOL": raise E3BundleError("installation policy mismatch")

    can=bundle.get("canary")
    if not isinstance(can,dict): raise E3BundleError("missing canary")
    if can.get("mode")!=FIXED_MODE or can.get("command_id")!=FIXED_COMMAND_ID: raise E3BundleError("wrong fixed canary")
    if can.get("authorization_ref")!=AUTH_REF or can.get("arbitrary_command_input") is not False: raise E3BundleError("canary authority mismatch")
    if can.get("installation_id")!=inst["installation_id"]: raise E3BundleError("installation id mismatch")
    if can.get("installation_fingerprint")!=sha256_json(inst): raise E3BundleError("installation fingerprint mismatch")
    if _root(can.get("install_root"))!=root: raise E3BundleError("canary root mismatch")
    if int(can.get("exit_code",-1))!=0 or str(can.get("stdout","")).strip()!=FIXED_STDOUT or not isinstance(can.get("stderr"),str): raise E3BundleError("canary output mismatch")
    if can.get("promotion_status")!="REAL_LOCAL_CANARY_EVIDENCE_CANDIDATE_UNATTESTED": raise E3BundleError("canary promotion mismatch")
    prov=can.get("provenance")
    if not isinstance(prov,dict) or prov.get("source")!="LOCAL_OWNER_WINDOWS_EXECUTION" or prov.get("observed_by")!="LOCAL_CANARY": raise E3BundleError("bad provenance")
    claimed=can.get("canary_sha256")
    body={k:v for k,v in can.items() if k!="canary_sha256"}
    if not isinstance(claimed,str) or claimed!=sha256_json(body): raise E3BundleError("canary hash mismatch")
    if not isinstance(can.get("evidence_sha256"),str) or not HEX64.match(can["evidence_sha256"]): raise E3BundleError("bad command evidence hash")

    health=bundle.get("health")
    if not isinstance(health,dict) or health.get("host")!="127.0.0.1" or int(health.get("port",0))!=8765 or health.get("observed") is not True: raise E3BundleError("health not loopback verified")

    files=bundle.get("package_files")
    if not isinstance(files,dict) or not REQUIRED_FILES.issubset(files): raise E3BundleError("required package files missing")
    for rel,digest in files.items():
        if rel.startswith(("/","\\")) or ".." in Path(rel).parts: raise E3BundleError("package path escape")
        if not isinstance(digest,str) or not HEX64.match(digest): raise E3BundleError("bad package digest")

    result={
      "status":"E3_EVIDENCE_READY_FOR_ONLINE_ATTESTATION",
      "mission_id":MISSION_ID,
      "authorization_ref":AUTH_REF,
      "installation_id":inst["installation_id"],
      "installation_fingerprint":sha256_json(inst),
      "canary_sha256":claimed,
      "package_manifest_sha256":sha256_json(files),
      "online_source_attested":False,
      "E3_promoted":False,
    }
    result["reconciliation_sha256"]=sha256_json(result)
    return result
