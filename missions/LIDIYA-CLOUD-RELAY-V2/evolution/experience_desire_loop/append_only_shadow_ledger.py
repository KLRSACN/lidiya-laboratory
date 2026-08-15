from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json, os
from typing import Mapping
GENESIS="0"*64
def canonical_bytes(payload:object)->bytes:
    return json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
def digest(payload:object)->str:
    return sha256(canonical_bytes(payload)).hexdigest()
class AppendOnlyShadowLedger:
    def __init__(self,workspace_root:Path,relative_path:str="edl_shadow/experience.jsonl"):
        self.root=workspace_root.resolve(); self.path=(self.root/relative_path).resolve()
        try: self.path.relative_to(self.root)
        except ValueError: raise ValueError("PATH_ESCAPE")
        self.path.parent.mkdir(parents=True,exist_ok=True)
    def _read(self)->list[dict]:
        if not self.path.exists(): return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]
    def verify(self)->bool:
        prev=GENESIS; dedupe=set()
        for index,rec in enumerate(self._read(),1):
            if rec.get("sequence")!=index or rec.get("prev_hash")!=prev: return False
            body=rec.get("body")
            if not isinstance(body,dict): return False
            if rec.get("record_hash")!=digest({"sequence":index,"prev_hash":prev,"body":body}): return False
            dk=body.get("dedupe_key")
            if not dk or dk in dedupe: return False
            dedupe.add(dk); prev=rec["record_hash"]
        return True
    def append(self,body:Mapping[str,object])->dict:
        required=("source_fingerprint","origin_namespace","verifier_envelope_hash","schema_version","timestamp","dedupe_key")
        if any(not body.get(k) for k in required): raise ValueError("INCOMPLETE_LEDGER_BODY")
        rows=self._read()
        if not self.verify(): raise ValueError("LEDGER_TAMPER_DETECTED")
        if any(r["body"]["dedupe_key"]==body["dedupe_key"] for r in rows): raise ValueError("DUPLICATE_LEDGER_EVENT")
        prev=rows[-1]["record_hash"] if rows else GENESIS; seq=len(rows)+1; b=dict(body)
        rec={"sequence":seq,"prev_hash":prev,"body":b}; rec["record_hash"]=digest(rec)
        with self.path.open("a",encoding="utf-8",newline="\n") as f:
            f.write(json.dumps(rec,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n"); f.flush(); os.fsync(f.fileno())
        return rec
