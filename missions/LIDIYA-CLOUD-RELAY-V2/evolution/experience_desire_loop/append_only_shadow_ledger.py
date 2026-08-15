from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import os
from typing import Mapping

GENESIS = "0" * 64


def canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(payload: object) -> str:
    return sha256(canonical_bytes(payload)).hexdigest()


class AppendOnlyShadowLedger:
    """Research-candidate append-only ledger with rollback/replay detection.

    The separate head checkpoint is workspace/path bound. A ledger that is ahead
    of or behind the accepted checkpoint fails closed and requires reconciliation.
    Runtime installation identity remains TEST_REQUIRED unless explicitly supplied.
    """

    def __init__(
        self,
        workspace_root: Path,
        relative_path: str = "edl_shadow/experience.jsonl",
        *,
        workspace_identity: str | None = None,
    ):
        self.root = workspace_root.resolve()
        self.path = (self.root / relative_path).resolve()
        try:
            self.path.relative_to(self.root)
        except ValueError:
            raise ValueError("PATH_ESCAPE")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.head_path = self.path.with_name(self.path.name + ".accepted_head.json")
        self.lock_path = self.path.with_name(self.path.name + ".writer.lock")
        self.workspace_identity = workspace_identity or "TEST_REQUIRED_UNBOUND_WORKSPACE_IDENTITY"
        self.ledger_binding_hash = digest(
            {
                "workspace_root": str(self.root),
                "workspace_identity": self.workspace_identity,
                "ledger_relative_path": str(self.path.relative_to(self.root)),
            }
        )

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def _read_checkpoint(self) -> dict | None:
        if not self.head_path.exists():
            return None
        try:
            value = json.loads(self.head_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return value if isinstance(value, dict) else None

    def _checkpoint_for(self, sequence: int, record_hash: str) -> dict[str, object]:
        body = {
            "schema_version": "EDL-SHADOW-LEDGER-HEAD-V0.2-TEST_REQUIRED",
            "sequence": sequence,
            "record_hash": record_hash,
            "ledger_binding_hash": self.ledger_binding_hash,
        }
        return {**body, "checkpoint_hash": digest(body)}

    def _write_checkpoint_atomic(self, checkpoint: Mapping[str, object]) -> None:
        tmp = self.head_path.with_name(self.head_path.name + ".tmp")
        raw = json.dumps(dict(checkpoint), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(raw + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.head_path)

    def _checkpoint_valid_for_rows(self, rows: list[dict]) -> bool:
        checkpoint = self._read_checkpoint()
        if not rows:
            return checkpoint is None
        if checkpoint is None:
            return False
        body = {
            "schema_version": checkpoint.get("schema_version"),
            "sequence": checkpoint.get("sequence"),
            "record_hash": checkpoint.get("record_hash"),
            "ledger_binding_hash": checkpoint.get("ledger_binding_hash"),
        }
        if checkpoint.get("checkpoint_hash") != digest(body):
            return False
        if checkpoint.get("ledger_binding_hash") != self.ledger_binding_hash:
            return False
        if checkpoint.get("sequence") != len(rows):
            return False
        if checkpoint.get("record_hash") != rows[-1].get("record_hash"):
            return False
        return True

    def verify(self) -> bool:
        prev = GENESIS
        dedupe = set()
        rows = self._read()
        for index, rec in enumerate(rows, 1):
            if rec.get("sequence") != index or rec.get("prev_hash") != prev:
                return False
            body = rec.get("body")
            if not isinstance(body, dict):
                return False
            if rec.get("record_hash") != digest({"sequence": index, "prev_hash": prev, "body": body}):
                return False
            dk = body.get("dedupe_key")
            if not dk or dk in dedupe:
                return False
            dedupe.add(dk)
            prev = rec["record_hash"]
        return self._checkpoint_valid_for_rows(rows)

    def _acquire_writer_lock(self) -> int:
        try:
            return os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ValueError("LEDGER_WRITER_LOCKED") from exc

    def _release_writer_lock(self, fd: int) -> None:
        try:
            os.close(fd)
        finally:
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass

    def append(self, body: Mapping[str, object]) -> dict:
        required = (
            "source_fingerprint",
            "origin_namespace",
            "verifier_envelope_hash",
            "schema_version",
            "timestamp",
            "dedupe_key",
        )
        if any(not body.get(k) for k in required):
            raise ValueError("INCOMPLETE_LEDGER_BODY")
        lock_fd = self._acquire_writer_lock()
        try:
            rows = self._read()
            if not self.verify():
                raise ValueError("LEDGER_TAMPER_REPLAY_OR_HEAD_MISMATCH")
            if any(r["body"]["dedupe_key"] == body["dedupe_key"] for r in rows):
                raise ValueError("DUPLICATE_LEDGER_EVENT")
            prev = rows[-1]["record_hash"] if rows else GENESIS
            seq = len(rows) + 1
            b = dict(body)
            rec = {"sequence": seq, "prev_hash": prev, "body": b}
            rec["record_hash"] = digest(rec)
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._write_checkpoint_atomic(self._checkpoint_for(seq, rec["record_hash"]))
            if not self.verify():
                raise ValueError("LEDGER_POST_APPEND_RECONCILIATION_FAILED")
            return rec
        finally:
            self._release_writer_lock(lock_fd)
