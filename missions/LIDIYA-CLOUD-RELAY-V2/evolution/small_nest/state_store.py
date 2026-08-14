from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Any, Dict

class StateStore:
    def __init__(self,path: str|Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
    def load(self) -> Dict[str,Any]:
        if not self.path.exists(): return {"schema_version":"1.0","runtime_state":"DORMANT","sequence":0,"checkpoint":None}
        return json.loads(self.path.read_text(encoding="utf-8"))
    def save(self,state: Dict[str,Any]) -> None:
        payload=json.dumps(state,sort_keys=True,separators=(",",":"),ensure_ascii=False)
        fd,tmp=tempfile.mkstemp(prefix=self.path.name+".",dir=str(self.path.parent))
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                f.write(payload); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    def checkpoint(self, **changes) -> Dict[str,Any]:
        state=self.load(); state.update(changes); state["sequence"]=int(state.get("sequence",0))+1; self.save(state); return state
