#!/usr/bin/env python3
"""Builder-decoupled process fault injection harness using the auditor CLI contract."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, tempfile, time
from pathlib import Path

def run(cmd, env=None, timeout=30):
    p=subprocess.run(cmd,text=True,capture_output=True,env=env,timeout=timeout)
    try: payload=json.loads(p.stdout) if p.stdout.strip() else None
    except json.JSONDecodeError: payload=None
    return {"command":cmd,"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"json":payload}

def snapshot(root:Path):
    out={}
    for p in sorted(root.rglob("*")):
        if p.is_file(): out[str(p.relative_to(root))]={"size":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
    return out

def invoke(adapter,root,op,args=(),inject_point=None,inject_mode=None):
    env=os.environ.copy()
    if inject_point: env["AUDIT_INJECT_POINT"]=inject_point
    if inject_mode: env["AUDIT_INJECT_MODE"]=inject_mode
    return run(adapter+[op,"--root",str(root),*args],env=env)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--adapter",nargs="+",required=True); ap.add_argument("--packet",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    cases=[("FI-01","before_function","raise"),("FI-02","after_function","raise"),("FI-03","before_side_effect","os_exit"),("FI-04","packet_write","partial_write"),("FI-05","fsync","fsync_fail"),("FI-06","atomic_replace","replace_fail"),("FI-07","checkpoint_update","replace_fail"),("FI-08","after_outbox_before_registry","os_exit"),("FI-09","after_registry_before_running_cleanup","os_exit")]
    report={"contract":"auditor_adapter_contract.json","generated_at":time.time(),"cases":[]}
    with tempfile.TemporaryDirectory(prefix="relay_fault_") as td:
        base=Path(td)
        for cid,point,mode in cases:
            root=base/cid; (root/"inbox").mkdir(parents=True); packet=root/"inbox"/a.packet.name; packet.write_bytes(a.packet.read_bytes())
            before=snapshot(root); result=invoke(a.adapter,root,"claim",["--packet",str(packet),"--owner","FAULT-A"],point,mode); after=snapshot(root)
            report["cases"].append({"id":cid,"injection_point":point,"mode":mode,"result":result,"before":before,"after":after})
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"cases":len(report["cases"]),"output":str(a.output)},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
