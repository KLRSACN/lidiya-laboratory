from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Any, Dict
from bridge_protocol import ReplayGuard, verify_envelope, canonical_json

FORBIDDEN_CONTEXT_KEYS={"raw_chat","conversation","messages","hidden_state","system_prompt"}
class BridgeSpoolError(ValueError): pass

def _has_forbidden(value: Any) -> bool:
    if isinstance(value,dict):
        return any(str(k).lower() in FORBIDDEN_CONTEXT_KEYS or _has_forbidden(v) for k,v in value.items())
    if isinstance(value,list): return any(_has_forbidden(v) for v in value)
    return False

class FileSpoolBridge:
    def __init__(self,workspace_root: str|Path,spool_rel: str=".lidiya/bridge"):
        self.root=Path(workspace_root).resolve(strict=False); self.spool=(self.root/spool_rel).resolve(strict=False)
        if os.path.commonpath([str(self.root),str(self.spool)]) != str(self.root): raise BridgeSpoolError("spool outside workspace")
        self.inbox=self.spool/"inbox"; self.outbox=self.spool/"outbox"; self.inbox.mkdir(parents=True,exist_ok=True); self.outbox.mkdir(parents=True,exist_ok=True)
        self.in_guard=ReplayGuard(); self.out_guard=ReplayGuard()
    def _write(self,folder: Path,envelope: Dict[str,Any]) -> Path:
        h=envelope["envelope_sha256"]; seq=envelope["sequence"]; target=folder/f"{seq:012d}-{h}.json"
        payload=canonical_json(envelope)
        fd,tmp=tempfile.mkstemp(prefix=target.name+".",dir=str(folder))
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as f: f.write(payload); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return target
    def ingest_task(self,envelope: Dict[str,Any]) -> Dict[str,Any]:
        if _has_forbidden(envelope): raise BridgeSpoolError("raw conversational context forbidden")
        verify_envelope(envelope); disposition=self.in_guard.accept(envelope)
        if disposition=="ALREADY_SEEN": return {"disposition":"ALREADY_SEEN_NO_WRITE"}
        p=self._write(self.inbox,envelope); return {"disposition":"ACCEPTED","path":str(p.relative_to(self.root)),"hash":envelope["envelope_sha256"]}
    def publish_evidence(self,envelope: Dict[str,Any]) -> Dict[str,Any]:
        if _has_forbidden(envelope): raise BridgeSpoolError("raw conversational context forbidden")
        verify_envelope(envelope); disposition=self.out_guard.accept(envelope)
        if disposition=="ALREADY_SEEN": return {"disposition":"ALREADY_SEEN_NO_WRITE"}
        p=self._write(self.outbox,envelope); return {"disposition":"PUBLISHED","path":str(p.relative_to(self.root)),"hash":envelope["envelope_sha256"]}
    def list_spool(self) -> Dict[str,list[str]]:
        return {"inbox":[p.name for p in sorted(self.inbox.glob("*.json"))],"outbox":[p.name for p in sorted(self.outbox.glob("*.json"))]}
