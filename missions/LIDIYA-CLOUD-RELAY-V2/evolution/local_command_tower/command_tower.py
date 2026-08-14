from __future__ import annotations
import argparse, json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
HERE=Path(__file__).resolve().parent
SMALL=HERE.parent/"small_nest"
if str(SMALL) not in sys.path: sys.path.insert(0,str(SMALL))
from command_broker import CommandBroker, BrokerRejected
from standby_router import route
from state_store import StateStore
from runtime import SmallNestRuntime

LOOPBACK={"127.0.0.1","localhost","::1"}

class Tower:
    def __init__(self,workspace_root,*,execute_enabled=False):
        self.root=Path(workspace_root).resolve(strict=False)
        self.state_store=StateStore(self.root/".lidiya"/"tower_state.json")
        self.small_nest=SmallNestRuntime(self.root/".lidiya"/"small_nest_state.json")
        self.broker=CommandBroker(self.root,execute_enabled=execute_enabled)
    def health(self):
        return {"ok":True,"tower":"READY","small_nest":self.small_nest.health(),"binding":"LOOPBACK_ONLY","sequence":self.state_store.load().get("sequence",0)}
    def wake(self):
        sn=self.small_nest.wake(); self.state_store.checkpoint(runtime_state="READY",last_event="WAKE"); return {"status":"WOKEN","small_nest":sn}
    def handle(self,event):
        decision=route(event)
        if decision["target"]=="COMMAND_BROKER":
            try: return {"route":decision,"evidence":self.broker.execute(event["command_envelope"])}
            except (BrokerRejected,KeyError) as e: return {"route":decision,"status":"REJECTED","reason":str(e)}
        if decision["target"]=="SMALL_NEST" and event.get("kind","").upper()=="WAKE": return {"route":decision,**self.wake()}
        return {"route":decision,"status":"ROUTED"}

def serve(tower: Tower,host="127.0.0.1",port=8765):
    if host not in LOOPBACK: raise ValueError("public bind forbidden")
    class Handler(BaseHTTPRequestHandler):
        def _send(self,obj,code=200):
            raw=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_GET(self): self._send(tower.health()) if self.path=="/health" else self._send({"error":"not found"},404)
        def do_POST(self):
            try:
                n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n) or b"{}")
            except Exception: return self._send({"error":"bad json"},400)
            if self.path=="/wake": self._send(tower.wake())
            elif self.path=="/event": self._send(tower.handle(data))
            else: self._send({"error":"not found"},404)
        def log_message(self,*args): pass
    ThreadingHTTPServer((host,port),Handler).serve_forever()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--workspace-root",required=True); ap.add_argument("--host",default="127.0.0.1"); ap.add_argument("--port",type=int,default=8765); ap.add_argument("--enable-exec",action="store_true",help="Enable broker execution only after independent C PASS and local canary gate."); ns=ap.parse_args()
    serve(Tower(ns.workspace_root,execute_enabled=ns.enable_exec),ns.host,ns.port)
if __name__=="__main__": main()
