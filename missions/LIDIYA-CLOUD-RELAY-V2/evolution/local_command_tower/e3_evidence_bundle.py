from __future__ import annotations
import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Dict

MISSION_ID = "LCR-EVOLUTION-0005"
AUTH_REF = "authorizations/LCR-EVOLUTION-0005-LOCAL-COMMAND-TOWER-24H-ADDENDUM-20260814.json"
FIXED_MODE = "WINDOWS_FIXED_HARMLESS_ECHO"
FIXED_COMMAND_ID = "LOCAL-CANARY-ECHO-001"
FIXED_STDOUT = "LIDIYA_CANARY"
PROMOTION = "E3_EVIDENCE_READY_FOR_ONLINE_ATTESTATION"
REQUIRED_FILES = frozenset({
    "evolution/small_nest/INSTALL_SMALL_NEST.ps1",
    "evolution/small_nest/START_SMALL_NEST.cmd",
    "evolution/small_nest/CHECK_SMALL_NEST_HEALTH.ps1",
    "evolution/small_nest/RUN_LOCAL_CANARY.cmd",
    "evolution/local_command_tower/local_canary.py",
    "evolution/local_command_tower/evidence_reconciler.py",
})
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class E3BundleError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _root(value: Any) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise E3BundleError("missing install_root")
    return Path(raw).resolve(strict=False)


def _safe_rel(rel: Any) -> str:
    raw = str(rel or "").replace("\\", "/")
    p = PurePosixPath(raw)
    if not raw or p.is_absolute() or ".." in p.parts or "." in p.parts or ":" in raw:
        raise E3BundleError("package path escape")
    normalized = p.as_posix()
    if normalized != raw:
        raise E3BundleError("noncanonical package path")
    return normalized


def validate_bundle(bundle: Dict[str, Any], *, workspace_root: str | Path | None = None) -> Dict[str, Any]:
    if not isinstance(bundle, dict) or bundle.get("schema_version") != "1.0":
        raise E3BundleError("bad schema")
    if bundle.get("mission_id") != MISSION_ID:
        raise E3BundleError("wrong mission")
    if bundle.get("authorization_ref") != AUTH_REF:
        raise E3BundleError("wrong authorization")
    if bundle.get("capture_mode") != "OWNER_WINDOWS_LOCAL_PACKAGE":
        raise E3BundleError("wrong capture mode")
    if bundle.get("promotion_status") != PROMOTION or bundle.get("E3_promoted") is not False:
        raise E3BundleError("premature promotion")

    inst = bundle.get("installation")
    if not isinstance(inst, dict) or inst.get("schema_version") != "1.0":
        raise E3BundleError("bad installation")
    try:
        uuid.UUID(str(inst.get("installation_id", "")))
    except Exception as exc:
        raise E3BundleError("invalid installation_id") from exc
    root = _root(inst.get("install_root"))
    expected_root = Path(workspace_root).resolve(strict=False) if workspace_root is not None else None
    if expected_root is not None and root != expected_root:
        raise E3BundleError("root mismatch")
    if inst.get("component") != "LIDIYA-LOCAL-NAV-COMMAND-TOWER-TYPE-1":
        raise E3BundleError("installation component mismatch")
    if inst.get("privilege") != "USER_SPACE" or inst.get("transport") != "LOOPBACK_AND_WORKSPACE_SPOOL":
        raise E3BundleError("installation policy mismatch")

    can = bundle.get("canary")
    if not isinstance(can, dict):
        raise E3BundleError("missing canary")
    if can.get("mode") != FIXED_MODE or can.get("command_id") != FIXED_COMMAND_ID:
        raise E3BundleError("wrong fixed canary")
    if can.get("authorization_ref") != AUTH_REF or can.get("arbitrary_command_input") is not False:
        raise E3BundleError("canary authority mismatch")
    if can.get("installation_id") != inst["installation_id"]:
        raise E3BundleError("installation id mismatch")
    if can.get("installation_fingerprint") != sha256_json(inst):
        raise E3BundleError("installation fingerprint mismatch")
    if _root(can.get("install_root")) != root:
        raise E3BundleError("canary root mismatch")
    try:
        exit_code = int(can.get("exit_code", -1))
    except Exception as exc:
        raise E3BundleError("invalid exit code") from exc
    if exit_code != 0 or str(can.get("stdout", "")).strip() != FIXED_STDOUT or not isinstance(can.get("stderr"), str):
        raise E3BundleError("canary output mismatch")
    if can.get("promotion_status") != "REAL_LOCAL_CANARY_EVIDENCE_CANDIDATE_UNATTESTED":
        raise E3BundleError("canary promotion mismatch")
    prov = can.get("provenance")
    if not isinstance(prov, dict) or prov.get("source") != "LOCAL_OWNER_WINDOWS_EXECUTION" or prov.get("observed_by") != "LOCAL_CANARY":
        raise E3BundleError("bad provenance")
    claimed = can.get("canary_sha256")
    body = {k: v for k, v in can.items() if k != "canary_sha256"}
    if not isinstance(claimed, str) or claimed != sha256_json(body):
        raise E3BundleError("canary hash mismatch")
    command_evidence_hash = can.get("evidence_sha256")
    if not isinstance(command_evidence_hash, str) or not HEX64.fullmatch(command_evidence_hash):
        raise E3BundleError("bad command evidence hash")

    health = bundle.get("health")
    if (
        not isinstance(health, dict)
        or health.get("host") != "127.0.0.1"
        or int(health.get("port", 0)) != 8765
        or health.get("observed") is not True
    ):
        raise E3BundleError("health not loopback verified")

    files = bundle.get("package_files")
    if not isinstance(files, dict) or set(files) != REQUIRED_FILES:
        raise E3BundleError("package manifest must contain exact required file set")
    for rel, digest in files.items():
        normalized = _safe_rel(rel)
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise E3BundleError("bad package digest")
        if expected_root is not None:
            file_path = (expected_root / Path(*PurePosixPath(normalized).parts)).resolve(strict=False)
            try:
                file_path.relative_to(expected_root)
            except ValueError as exc:
                raise E3BundleError("package path escaped workspace") from exc
            if not file_path.is_file():
                raise E3BundleError("package file missing from workspace")
            if sha256_file(file_path) != digest:
                raise E3BundleError("package file digest mismatch")

    result = {
        "status": PROMOTION,
        "mission_id": MISSION_ID,
        "authorization_ref": AUTH_REF,
        "installation_id": inst["installation_id"],
        "installation_fingerprint": sha256_json(inst),
        "canary_sha256": claimed,
        "command_evidence_sha256": command_evidence_hash,
        "package_manifest_sha256": sha256_json(files),
        "online_source_attested": False,
        "E3_promoted": False,
    }
    result["reconciliation_sha256"] = sha256_json(result)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--workspace-root", required=True)
    ns = ap.parse_args()
    bundle_path = Path(ns.bundle).resolve(strict=False)
    workspace_root = Path(ns.workspace_root).resolve(strict=False)
    try:
        bundle_path.relative_to(workspace_root)
    except ValueError as exc:
        raise E3BundleError("bundle path outside workspace") from exc
    data = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
    print(json.dumps(validate_bundle(data, workspace_root=workspace_root), sort_keys=True))


if __name__ == "__main__":
    main()
