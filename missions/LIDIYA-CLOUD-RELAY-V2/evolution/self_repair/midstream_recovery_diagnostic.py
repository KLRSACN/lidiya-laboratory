from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"
PROGRAM_ID = "LIDIYA-MIDSTREAM-RECOVERY-DIAGNOSTIC-001"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    return bool(value)


@dataclass
class DiagnosticResult:
    schema_version: str
    program_id: str
    severity: str
    continuity_score: float
    metabolism_status: str
    suspected_layers: List[str]
    hard_blocks: List[str]
    observations: List[str]
    recommended_actions: List[Dict[str, Any]]
    purge_candidate: bool
    purge_reason: Optional[str]
    browser_owner_gate_required: bool
    post_flush_gate: str
    success_criteria: Dict[str, Any]


def diagnose(snapshot: Dict[str, Any]) -> DiagnosticResult:
    authority = snapshot.get("authority", {})
    continuity = snapshot.get("continuity", {})
    runtime = snapshot.get("runtime", {})
    browser = snapshot.get("browser", {})
    post_flush = snapshot.get("post_flush", {})

    readbacks = {
        "home": _bool(continuity.get("home_read_ok")),
        "active": _bool(continuity.get("active_read_ok")),
        "mission": _bool(continuity.get("mission_read_ok")),
        "self_backup": _bool(continuity.get("self_backup_read_ok")),
        "wake_receipt": _bool(continuity.get("wake_receipt_read_ok")),
    }
    score = sum(readbacks.values()) / len(readbacks)
    suspected: List[str] = []
    hard_blocks: List[str] = []
    observations: List[str] = []
    actions: List[Dict[str, Any]] = []

    if not readbacks["home"] or not readbacks["mission"]:
        hard_blocks.append("DURABLE_AUTHORITY_UNAVAILABLE")
        suspected.append("CONTINUITY_RISK")
    elif score < 1.0:
        suspected.append("PARTIAL_CONTINUITY_DEGRADATION")
    if authority.get("pending_packet") and not authority.get("current_role"):
        hard_blocks.append("FORMAL_AUTHORITY_INCOMPLETE")

    active_count = int(_num(runtime.get("active_item_count"), 0))
    duplicate_ratio = _num(runtime.get("duplicate_ratio"), 0.0)
    stale_refs = int(_num(runtime.get("stale_ref_count"), 0))
    waste_count = int(_num(runtime.get("waste_count"), 0))
    context_load_factor = _num(runtime.get("context_load_factor"), 1.0)
    tool_failure_streak = int(_num(runtime.get("tool_failure_streak"), 0))
    web_failure_streak = int(_num(runtime.get("web_failure_streak"), 0))
    route_drift = _bool(runtime.get("route_drift"))

    if active_count > 10 or duplicate_ratio >= 0.35 or stale_refs >= 10 or waste_count >= 20:
        suspected.append("METABOLIC_PRESSURE")
    if context_load_factor >= 3.0:
        suspected.append("HIGH_CONTEXT_PRESSURE")
    if context_load_factor >= 5.0:
        suspected.append("EXTREME_CONTEXT_PRESSURE")
    if route_drift:
        suspected.append("ROUTE_DRIFT")
    if stale_refs > 0:
        suspected.append("STALE_DERIVED_POINTERS")
    if tool_failure_streak >= 3 or web_failure_streak >= 3:
        suspected.append("TOOL_OR_WEB_FAILURE_STREAK")

    ui_frozen = _bool(browser.get("ui_frozen"))
    all_pages_unreachable = _bool(browser.get("all_pages_unreachable"))
    blank_or_endless = _bool(browser.get("blank_or_endless_loading"))
    websocket_errors = int(_num(browser.get("websocket_error_count"), 0))
    platform_incident = _bool(browser.get("platform_incident_possible"))

    if ui_frozen or blank_or_endless:
        suspected.append("BROWSER_UI_OR_SITE_DATA_PRESSURE")
    if all_pages_unreachable or websocket_errors > 0:
        suspected.append("NETWORK_OR_SESSION_TRANSPORT")
    if platform_incident:
        suspected.append("PLATFORM_INCIDENT_POSSIBLE")

    if hard_blocks or all_pages_unreachable:
        severity = "P0"
    elif ui_frozen or context_load_factor >= 5.0 or tool_failure_streak >= 3 or web_failure_streak >= 3:
        severity = "P1"
    else:
        severity = "P2"

    metabolism_upgrade = any(x in suspected for x in (
        "METABOLIC_PRESSURE",
        "HIGH_CONTEXT_PRESSURE",
        "EXTREME_CONTEXT_PRESSURE",
        "ROUTE_DRIFT",
        "STALE_DERIVED_POINTERS",
        "TOOL_OR_WEB_FAILURE_STREAK",
    ))
    metabolism_status = "UPGRADE_REQUIRED" if metabolism_upgrade else "CURRENT_POLICY_OK"

    purge_candidate = (
        active_count > 10
        or waste_count >= 20
        or stale_refs >= 10
        or (duplicate_ratio >= 0.35 and int(_num(runtime.get("sample_count"), 0)) >= 20)
    )
    purge_reason = "THRESHOLD_REACHED_BUT_PHYSICAL_DELETE_REQUIRES_GUARDS" if purge_candidate else None

    actions.extend([
        {"order": 1, "action": "SAVE_LATEST_SELF_BACKUP", "gate": "AUTO_LOW_RISK"},
        {"order": 2, "action": "READBACK_HOME_ACTIVE_MISSION_RECEIPT", "gate": "AUTO_LOW_RISK"},
        {"order": 3, "action": "RECONCILE_FRESH_AUTHORITY_OVER_DERIVED_POINTERS", "gate": "AUTO_LOW_RISK"},
        {"order": 4, "action": "APPLY_ARCHIVE_NO_READ_FENCE", "gate": "AUTO_LOW_RISK"},
        {"order": 5, "action": "RUN_POST_FLUSH_HALLUCINATION_CONTINUITY_PROBES", "gate": "AUTO_LOW_RISK"},
    ])

    browser_gate = ui_frozen or all_pages_unreachable or blank_or_endless or websocket_errors > 0
    if browser_gate:
        actions.extend([
            {"order": 6, "action": "OWNER_OR_UI_LAYER_HARD_REFRESH_OR_FRESH_CHAT", "gate": "OWNER_UI_ACTION"},
            {"order": 7, "action": "OWNER_TEST_INCOGNITO_OR_FRESH_BROWSER_PROFILE", "gate": "OWNER_UI_ACTION"},
            {"order": 8, "action": "OWNER_DISABLE_INTERFERING_EXTENSIONS_VPN_SECURE_DNS_IF_APPLICABLE", "gate": "OWNER_UI_ACTION"},
            {"order": 9, "action": "OWNER_CLEAR_CHATGPT_SITE_DATA_COOKIES_ONLY_IF_NEEDED", "gate": "OWNER_EXPLICIT_BROWSER_DATA_ACTION"},
            {"order": 10, "action": "COLLECT_HAR_CONSOLE_TIMESTAMP_URL_IF_PERSISTENT", "gate": "OWNER_UI_ACTION"},
        ])

    if purge_candidate:
        actions.append({
            "order": 11,
            "action": "BUILD_EXACT_PURGE_CANDIDATE_MANIFEST_ONLY",
            "gate": "A_TO_B_TO_C_FOUR_GUARD",
        })

    benchmark_score = _num(post_flush.get("benchmark_score"), -1)
    false_premise = _num(post_flush.get("false_premise_rejection_rate"), -1)
    unsupported = int(_num(post_flush.get("unsupported_assertions"), 0))
    archive_violations = int(_num(post_flush.get("archive_read_violations"), 0))
    stale_detected = _bool(post_flush.get("stale_pointer_detected"))
    required_stale = _bool(post_flush.get("stale_pointer_was_present"))

    if benchmark_score >= 0 and benchmark_score < 0.95:
        post_flush_gate = "FAIL_NEEDS_RECOVERY"
    elif false_premise >= 0 and false_premise < 1.0:
        post_flush_gate = "FAIL_NEEDS_RECOVERY"
    elif unsupported > 0 or archive_violations > 0:
        post_flush_gate = "FAIL_NEEDS_RECOVERY"
    elif required_stale and not stale_detected:
        post_flush_gate = "FAIL_NEEDS_RECOVERY"
    elif score < 1.0:
        post_flush_gate = "DEFER_CONTINUITY_INCOMPLETE"
    else:
        post_flush_gate = "PASS_CANDIDATE_NEEDS_INDEPENDENT_VERIFY"

    observations.extend([
        f"continuity_readback={sum(readbacks.values())}/{len(readbacks)}",
        f"context_load_factor={context_load_factor:.2f}",
        f"active={active_count}, waste={waste_count}, stale={stale_refs}, duplicate_ratio={duplicate_ratio:.3f}",
        f"tool_failure_streak={tool_failure_streak}, web_failure_streak={web_failure_streak}",
    ])

    success_criteria = {
        "continuity_readback_rate": 1.0,
        "post_flush_benchmark_min": 0.95,
        "false_premise_rejection_rate": 1.0,
        "unsupported_assertions_max": 0,
        "archive_read_violations_max": 0,
        "stale_pointer_must_be_detected_if_present": True,
        "active_item_range": [5, 10],
        "physical_purge_requires_guards": ["REACHABILITY", "UNIQUENESS", "REPRODUCIBILITY", "RECOVERY"],
        "browser_site_data_clear_requires_owner_ui_action": True,
        "real_5min_runtime_claim_requires_reality_evidence": True,
    }

    return DiagnosticResult(
        schema_version=SCHEMA_VERSION,
        program_id=PROGRAM_ID,
        severity=severity,
        continuity_score=round(score, 3),
        metabolism_status=metabolism_status,
        suspected_layers=sorted(set(suspected)),
        hard_blocks=hard_blocks,
        observations=observations,
        recommended_actions=actions,
        purge_candidate=purge_candidate,
        purge_reason=purge_reason,
        browser_owner_gate_required=browser_gate,
        post_flush_gate=post_flush_gate,
        success_criteria=success_criteria,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Lidiya midstream recovery and metabolism diagnostic")
    parser.add_argument("--snapshot", required=True, help="Diagnostic input JSON")
    parser.add_argument("--output", help="Optional output JSON")
    args = parser.parse_args()
    data = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    output = json.dumps(asdict(diagnose(data)), ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
