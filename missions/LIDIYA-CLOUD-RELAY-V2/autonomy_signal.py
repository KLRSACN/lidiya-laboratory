from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_dedupe_key(*parts: Any) -> str:
    normalized = "|".join("" if part is None else str(part) for part in parts)
    return "lcr-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def evidence_refs(state: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key, value in state.items():
        if key.endswith("_evidence") and isinstance(value, str) and value:
            refs.append(value)
    closure = state.get("closure_evidence")
    if isinstance(closure, str) and closure:
        refs.append(closure)
    return sorted(set(refs))


def activation_gate(state: dict[str, Any]) -> dict[str, Any] | None:
    active = state.get("human_gate")
    if isinstance(active, dict) and active:
        return {
            "code": active.get("code") or "HUMAN_GATE",
            "blocker": active.get("blocker") or "Human decision required.",
            "required_action": active.get("required_action") or "Human review required.",
            "status": "ACTIVE",
        }

    deferred = state.get("deferred_human_gate")
    agentic = (state.get("cloud_activation") or {}).get("agentic_engine")
    if isinstance(deferred, dict) and deferred:
        return {
            "code": deferred.get("code") or "DEFERRED_HUMAN_GATE",
            "blocker": deferred.get("blocker") or "Deferred human decision remains unresolved.",
            "required_action": "Explicitly authorize the deferred action before execution.",
            "status": deferred.get("status") or "DEFERRED",
        }
    if isinstance(agentic, str) and ("HUMAN_GATE" in agentic or "PENDING_AUTH" in agentic):
        return {
            "code": "CLOUD_ACTIVATION_REQUIRES_HUMAN",
            "blocker": "Cloud agent activation remains gated by authentication and/or default-branch entrypoint authorization.",
            "required_action": "Explicit human authorization is required before crossing the activation boundary.",
            "status": "DEFERRED",
        }
    return None


def derive_next_issue(state: dict[str, Any]) -> dict[str, Any] | None:
    mission_id = state.get("mission_id") or "UNKNOWN_MISSION"
    gate = activation_gate(state)
    if gate:
        title = f"{mission_id}: resolve {gate['code']}"
        dedupe = stable_dedupe_key(mission_id, "activation_gate", gate["code"], gate["blocker"])
        return {
            "dedupe_key": dedupe,
            "kind": "activation_gate",
            "priority": "P0",
            "title": title,
            "summary": gate["blocker"],
            "acceptance": [gate["required_action"]],
            "requires_human": True,
            "can_auto_execute": False,
        }

    pending = state.get("pending_packet")
    if pending:
        role = state.get("current_role") or state.get("next_role") or "UNKNOWN_ROLE"
        title = f"{mission_id}: process pending handoff for {role}"
        dedupe = stable_dedupe_key(mission_id, "handoff", pending, role)
        return {
            "dedupe_key": dedupe,
            "kind": "handoff",
            "priority": "P1",
            "title": title,
            "summary": f"Consume and process {pending} exactly once as {role}.",
            "acceptance": [
                "Packet hash is verified before consumption.",
                "Lease ownership is valid for the target role.",
                "Result is persisted before control is handed off.",
            ],
            "requires_human": False,
            "can_auto_execute": True,
        }

    if state.get("status") == "IDLE" and state.get("mission_result") == "PASS":
        return None

    status = state.get("status") or "UNKNOWN"
    role = state.get("current_role") or "UNKNOWN_ROLE"
    title = f"{mission_id}: advance from {status}"
    dedupe = stable_dedupe_key(mission_id, "advance_state", status, role, state.get("step_id"))
    return {
        "dedupe_key": dedupe,
        "kind": "advance_state",
        "priority": "P2",
        "title": title,
        "summary": f"Advance the next smallest authorized step from {status} under {role}.",
        "acceptance": [
            "Work stays inside current authorization boundaries.",
            "A reproducible evidence artifact is recorded.",
            "The next role is handed a durable packet or the mission returns to a safe baseline.",
        ],
        "requires_human": False,
        "can_auto_execute": True,
    }


def progress_summary(state: dict[str, Any]) -> str:
    mission_id = state.get("mission_id") or "UNKNOWN_MISSION"
    status = state.get("status") or "UNKNOWN"
    role = state.get("current_role") or "UNKNOWN_ROLE"
    step = state.get("step_id")
    attempt = state.get("attempt")
    gate = activation_gate(state)
    parts = [f"{mission_id} step={step} attempt={attempt} status={status} role={role}."]
    if state.get("pending_packet"):
        parts.append(f"Pending handoff: {state['pending_packet']}.")
    if gate:
        parts.append(f"Activation gate: {gate['code']} ({gate['status']}).")
    rollback = (state.get("metabolism") or {}).get("rollback_anchor") or state.get("stable_ref")
    if rollback:
        parts.append(f"Rollback anchor: {rollback}.")
    return " ".join(parts)


def generate_signal(
    state: dict[str, Any],
    *,
    generated_at: str | None = None,
    source_ref: str = "state/MISSION_STATE.json",
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    next_issue = derive_next_issue(state)
    gate = activation_gate(state)
    signal = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "source_ref": source_ref,
        "mission": {
            "mission_id": state.get("mission_id"),
            "status": state.get("status"),
            "step_id": state.get("step_id"),
            "attempt": state.get("attempt"),
            "current_role": state.get("current_role"),
            "next_role": state.get("next_role"),
            "mission_result": state.get("mission_result"),
        },
        "progress": {
            "summary": progress_summary(state),
            "pending_packet": state.get("pending_packet"),
            "rollback_anchor": (state.get("metabolism") or {}).get("rollback_anchor") or state.get("stable_ref"),
            "evidence_refs": evidence_refs(state),
            "cloud_activation": state.get("cloud_activation") or {},
            "activation_gate": gate,
            "completion_claim": "PASS" if state.get("mission_result") == "PASS" else "NOT_COMPLETE",
        },
        "next_issue": next_issue,
    }
    signal["signal_sha256"] = hashlib.sha256(canonical_json(signal).encode("utf-8")).hexdigest()
    return signal


def render_markdown(signal: dict[str, Any]) -> str:
    mission = signal["mission"]
    progress = signal["progress"]
    lines = [
        "# Lidiya Cloud Relay — Development Progress",
        "",
        f"- Generated: `{signal['generated_at']}`",
        f"- Mission: `{mission.get('mission_id')}`",
        f"- State: `{mission.get('status')}`",
        f"- Step / attempt: `{mission.get('step_id')}` / `{mission.get('attempt')}`",
        f"- Current role: `{mission.get('current_role')}`",
        f"- Completion claim: `{progress.get('completion_claim')}`",
        "",
        "## Progress",
        progress.get("summary") or "",
    ]
    refs = progress.get("evidence_refs") or []
    if refs:
        lines.extend(["", "### Evidence"])
        lines.extend(f"- `{ref}`" for ref in refs)

    issue = signal.get("next_issue")
    lines.extend(["", "## Next issue"])
    if not issue:
        lines.append("No next issue: mission is at verified PASS / IDLE.")
    else:
        lines.extend(
            [
                f"**{issue['title']}**",
                "",
                f"- Key: `{issue['dedupe_key']}`",
                f"- Kind: `{issue['kind']}`",
                f"- Priority: `{issue['priority']}`",
                f"- Requires human: `{str(issue['requires_human']).lower()}`",
                f"- Auto-executable: `{str(issue['can_auto_execute']).lower()}`",
                "",
                issue["summary"],
                "",
                "### Acceptance",
            ]
        )
        lines.extend(f"- {item}" for item in issue.get("acceptance") or [])
    lines.extend(["", f"Signal SHA-256: `{signal['signal_sha256']}`", ""])
    return "\n".join(lines)


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_signal(signal: dict[str, Any], json_out: Path, md_out: Path) -> None:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(signal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_out.write_text(render_markdown(signal), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate LCR progress and next-issue signal from durable state.")
    parser.add_argument("--state", default="state/MISSION_STATE.json")
    parser.add_argument("--json-out", default="signals/AUTONOMY-0002-LATEST.json")
    parser.add_argument("--md-out", default="signals/AUTONOMY-0002-LATEST.md")
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args()

    state_path = Path(args.state)
    signal = generate_signal(
        load_state(state_path),
        generated_at=args.generated_at,
        source_ref=str(state_path).replace("\\", "/"),
    )
    write_signal(signal, Path(args.json_out), Path(args.md_out))
    print(json.dumps(signal, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
