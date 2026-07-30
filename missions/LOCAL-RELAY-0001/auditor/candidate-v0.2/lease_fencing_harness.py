#!/usr/bin/env python3
"""Independent lease-generation fencing test with concurrent stale/current submissions."""
from __future__ import annotations
import argparse, json, os, subprocess, tempfile, time
from pathlib import Path

def call(adapter,root,args,env=None):
    p=subprocess.run(adapter+args+["--root",str(root)],text=True,capture_output=True,env=env,timeout=30)
    try: data=json.loads(p.stdout)
    except Exception: data=None
    return {"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"json":data}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--adapter",nargs="+",required=True); ap.add_argument("--packet",type=Path,required=True); ap.add_argument("--result",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="relay_fence_") as td:
        root=Path(td); (root/"inbox").mkdir(); packet=root/"inbox"/a.packet.name; packet.write_bytes(a.packet.read_bytes())
        claim_a=call(a.adapter,root,["claim","--packet",str(packet),"--owner","A"]); ja=claim_a["json"] or {}; task=ja.get("task_id"); ca=ja.get("claim_id"); g1=ja.get("lease_generation")
        recover=call(a.adapter,root,["recover","--now",str(time.time()+3600)])
        claim_b=call(a.adapter,root,["claim","--packet",str(packet),"--owner","B"]); jb=claim_b["json"] or {}; cb=jb.get("claim_id"); g2=jb.get("lease_generation")
        hb_a=call(a.adapter,root,["heartbeat","--task-id",str(task),"--owner","A","--claim-id",str(ca),"--lease-generation",str(g1)])
        submit=["submit-result","--task-id",str(task),"--result",str(a.result)]; barrier=root/"submit.barrier"; env=os.environ.copy(); env["AUDIT_START_BARRIER"]=str(barrier)
        pa=subprocess.Popen(a.adapter+submit+["--owner","A","--claim-id",str(ca),"--lease-generation",str(g1),"--root",str(root)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        pb=subprocess.Popen(a.adapter+submit+["--owner","B","--claim-id",str(cb),"--lease-generation",str(g2),"--root",str(root)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        barrier.write_text("go",encoding="utf-8"); oa,ea=pa.communicate(timeout=30); ob,eb=pb.communicate(timeout=30)
        final=call(a.adapter,root,["read-completed-record","--task-id",str(task)])
        assertions={"g1_is_1":g1==1,"g2_is_2":g2==2,"stale_heartbeat_rejected":hb_a["exit_code"]!=0,"only_b_submit_succeeds":pa.returncode!=0 and pb.returncode==0}
        report={"claim_a":claim_a,"recover":recover,"claim_b":claim_b,"stale_heartbeat":hb_a,"concurrent_submit":{"A":{"exit_code":pa.returncode,"stdout":oa,"stderr":ea},"B":{"exit_code":pb.returncode,"stdout":ob,"stderr":eb}},"completed":final,"assertions":assertions,"pass":all(assertions.values())}
        a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2),encoding="utf-8"); print(json.dumps({"pass":report["pass"],"assertions":assertions},indent=2)); return 0 if report["pass"] else 1
if __name__=="__main__": raise SystemExit(main())
