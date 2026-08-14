from __future__ import annotations
import argparse, json, time
from state_store import StateStore

class SmallNestRuntime:
    def __init__(self,state_path): self.store=StateStore(state_path)
    def wake(self): return self.store.checkpoint(runtime_state="READY",last_wake=time.time(),offline_held=False)
    def health(self):
        s=self.store.load(); return {"ok":True,"runtime_state":s.get("runtime_state"),"sequence":s.get("sequence",0),"offline_held":bool(s.get("offline_held",False))}
    def hold_offline(self,resume_fingerprint): return self.store.checkpoint(runtime_state="OFFLINE_HELD_UNVERIFIED",offline_held=True,checkpoint=resume_fingerprint)
    def reconnect(self,verified_resume_fingerprint):
        s=self.store.load()
        if not s.get("offline_held"): return {"status":"NO_OFFLINE_HOLD"}
        if s.get("checkpoint") != verified_resume_fingerprint: return {"status":"HOLD_FINGERPRINT_MISMATCH"}
        out=self.store.checkpoint(runtime_state="READY",offline_held=False); return {"status":"RESUMED","sequence":out["sequence"]}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--state",default=".lidiya/small_nest_state.json"); ap.add_argument("action",choices=["wake","health"]); ns=ap.parse_args()
    rt=SmallNestRuntime(ns.state); print(json.dumps(rt.wake() if ns.action=="wake" else rt.health(),ensure_ascii=False))
if __name__=="__main__": main()
