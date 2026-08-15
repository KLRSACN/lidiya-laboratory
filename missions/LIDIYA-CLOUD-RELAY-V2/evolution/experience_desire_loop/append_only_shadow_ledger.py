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

    The local accepted-head is path/workspace bound. When ``trusted_anchor_root``
    is supplied, a second monotonic anchor is retained outside the workspace
    rollback domain. Restoring an older ledger+local-head pair then fails closed
    against that independently retained anchor.

    The trusted anchor location/identity is still a research integration point;
    production installation/reconciler binding remains TEST_REQUIRED.
    """

    def __init__(
        self,
        workspace_root: Path,
        relative_path: str = "edl_shadow/experience.jsonl",
        *,
        workspace_identity: str | None = None,
        trusted_anchor_root: Path | None = None,
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

        self.trusted_anchor_root: Path | None = None
        self.trusted_anchor_path: Path | None = None
        if trusted_anchor_root is not None:
            anchor_root = trusted_anchor_root.resolve()
            # The monotonic anchor must not live inside the rollback domain.
            try:
                anchor_root.relative_to(self.root)
            except ValueError:
                pass
            else:
                raise ValueError("TRUSTED_ANCHOR_INSIDE_WORKSPACE")
            anchor_root.mkdir(parents=True, exist_ok=True)
            self.trusted_anchor_root = anchor_root
            self.trusted_anchor_path = anchor_root / f"{self.ledger_binding_hash}.monotonic_head.json"

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]

    @staticmethod
    def _read_json_dict(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return value if isinstance(value, dict) else None

    def _read_checkpoint(self) -> dict | None:
        return self._read_json_dict(self.head_path)

    def _read_trusted_anchor(self) -> dict | None:
        if self.trusted_anchor_path is None:
            return None
        return self._read_json_dict(self.trusted_anchor_path)

    def _checkpoint_for(self, sequence: int, record_hash: str) -> dict[str, object]:
        body = {
            "schema_version": "EDL-SHADOW-LEDGER-HEAD-V0.3-TEST_REQUIRED",
            "sequence": sequence,
            "record_hash": record_hash,
            "ledger_binding_hash": self.ledger_binding_hash,
        }
        return {**body, "checkpoint_hash": digest(body)}

    def _trusted_anchor_for(self, sequence: int, record_hash: str) -> dict[str, object]:
        body = {
            "schema_version": "EDL-SHADOW-LEDGER-MONOTONIC-ANCHOR-V0.1-TEST_REQUIRED",
            "sequence": sequence,
            "record_hash": record_hash,
            "ledger_binding_hash": self.ledger_binding_hash,
            "workspace_identity": self.workspace_identity,
        }
        return {**body, "anchor_hash": digest(body)}

    @staticmethod
    def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
        tmp = path.with_name(path.name + ".tmp")
        raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(raw + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _write_checkpoint_atomic(self, checkpoint: Mapping[str, object]) -> None:
        self._write_json_atomic(self.head_path, checkpoint)

    def _write_trusted_anchor_atomic(self, anchor: Mapping[str, object]) -> None:
        if self.trusted_anchor_path is None:
            return
        prior = self._read_trusted_anchor()
        if prior is not None:
            prior_sequence = prior.get("sequence")
            if not isinstance(prior_sequence, int):
                raise ValueError("TRUSTED_ANCHOR_INVALID")
            new_sequence = anchor.get("sequence")
            if not isinstance(new_sequence, int) or new_sequence < prior_sequence:
                raise ValueError("TRUSTED_ANCHOR_MONOTONICITY_VIOLATION")
            if new_sequence == prior_sequence and prior.get("record_hash") != anchor.get("record_hash"):
                raise ValueError("TRUSTED_ANCHOR_FORK")
        self._write_json_atomic(self.trusted_anchor_path, anchor)

    def _checkpoint_valid_for_rows(self, rows: list[dict]) -> bool:
        checkpoint = self._read_checkpoint()
        if not rows:
            return checkpoint is None and self._read_trusted_anchor() is None
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

        if self.trusted_anchor_path is not None:
            anchor = self._read_trusted_anchor()
            if anchor is None:
                return False
            anchor_body = {
                "schema_version": anchor.get("schema_version"),
                "sequence": anchor.get("sequence"),
                "record_hash": anchor.get("record_hash"),
                "ledger_binding_hash": anchor.get("ledger_binding_hash"),
                "workspace_identity": anchor.get("workspace_identity"),
            }
            if anchor.get("anchor_hash") != digest(anchor_body):
                return False
            if anchor.get("ledger_binding_hash") != self.ledger_binding_hash:
                return False
            if anchor.get("workspace_identity") != self.workspace_identity:
                return False
            # Exact equality intentionally fails both rollback and crash-ahead.
            if anchor.get("sequence") != len(rows):
                return False
            if anchor.get("record_hash") != rows[-1].get("record_hash"):
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
            self._write_trusted_anchor_atomic(self._trusted_anchor_for(seq, rec["record_hash"]))
            if not self.verify():
                raise ValueError("LEDGER_POST_APPEND_RECONCILIATION_FAILED")
            return rec
        finally:
            self._release_writer_lock(lock_fd)
