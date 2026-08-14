from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path
from command_broker import CommandBroker, AUTH_REF
class CanaryError(RuntimeError): pass
def _hash(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def load_installation_metadata(root: Path):
    path=root/".lidiya"/"installation.json"
    if not path.is_file(): raise CanaryError("installation metadata required for Windows owner canary")
    data=json.loads(path.read_text(encoding="utf-8")); iid=str(data.get("installation_id","")).strip()
    if not iid: raise CanaryError("installation_id required")
    if Path(data.get("workspace_root","")).resolve(strict=False)!=root.resolve(strict=False): raise CanaryError("installation workspace mismatch")
    if data.get("secrets_present") not in (False,None): raise CanaryError("invalid installation metadata")
    return data
class FakeExecutor:
    def __init__(self): self.calls=0
    def __call__(self,env): self.calls+=1; return {"stdout":"LIDIYA_CANARY\n","stderr":"","exit_code":0}
def _envelope(root:Path,dedupe="local-canary-echo"):
    return {"command_id":"LOCAL-CANARY-ECHO-001","mission_id":"LCR-EVOLUTION-0005","authorization_ref":AUTH_REF,"cwd":str(root),"shell":"cmd","command":"echo LIDIYA_CANARY","risk_class":"LOW","expected_outputs":["LIDIYA_CANARY"],"timeout":10,"rollback_or_noop":"NOOP","dedupe_key":dedupe}
def run_isolated_canary(workspace_root):
    root=Path(workspace_root).resolve(strict=False); (root/".lidiya").mkdir(parents=True,exist_ok=True)
    import sys; small=root/"evolution"/"small_nest"
    if not small.exists(): small=Path(__file__).resolve().parent.parent/"small_nest"
    if str(small) not in sys.path: sys.path.insert(0,str(small))
    from runtime import SmallNestRuntime
    rt=SmallNestRuntime(root/".lidiya"/"small_nest_canary_state.json"); wake=rt.wake(); fp="resume-canary-fp"; held=rt.hold_offline(fp); wrong=rt.reconnect("wrong")
    fx=FakeExecutor(); broker=CommandBroker(root,execute_enabled=True,executor=fx); first=broker.execute(_envelope(root)); duplicate=broker.execute(_envelope(root)); resumed=rt.reconnect(fp)
    out={"mode":"ISOLATED_FAKE_EXECUTOR","wake_state":wake["runtime_state"],"command_exit_code":first["exit_code"],"command_evidence_sha256":first["evidence_sha256"],"duplicate_disposition":duplicate["disposition"],"executor_calls":fx.calls,"offline_state":held["runtime_state"],"wrong_resume":wrong["status"],"matching_resume":resumed["status"],"owner_machine_touched":False,"promotion_status":"CANARY_CANDIDATE_ONLY"}; out["canary_sha256"]=_hash(out); return out
def run_windows_owner_canary(workspace_root):
    if os.name!="nt": raise CanaryError("Windows owner canary requires Windows")
    root=Path(workspace_root).resolve(strict=False); meta=load_installation_metadata(root); broker=CommandBroker(root,execute_enabled=True); result=broker.execute(_envelope(root,"owner-win-canary-echo"))
    out={"mode":"WINDOWS_FIXED_HARMLESS_ECHO","command_id":result["command_id"],"stdout":result["stdout"],"stderr":result["stderr"],"exit_code":result["exit_code"],"evidence_sha256":result["evidence_sha256"],"authorization_ref":AUTH_REF,"arbitrary_command_input":False,"installation_id":meta["installation_id"],"provenance":{"source":"LOCAL_OWNER_WINDOWS_EXECUTION","observed_by":"LOCAL_CANARY"},"promotion_status":"E3_CANDIDATE_REAL_LOCAL_EVIDENCE_PENDING_ONLINE_SOURCE_ATTESTATION"}; out["canary_sha256"]=_hash(out); (root/".lidiya"/"local_canary_evidence.json").write_text(json.dumps(out,sort_keys=True,indent=2,ensure_ascii=False),encoding="utf-8"); return out
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--workspace-root",required=True); ap.add_argument("--execute-windows",action="store_true"); ns=ap.parse_args(); print(json.dumps(run_windows_owner_canary(ns.workspace_root) if ns.execute_windows else run_isolated_canary(ns.workspace_root),ensure_ascii=False))
if __name__=="__main__": main()
