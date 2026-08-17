from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

PROGRAM_ID = "LIDIYA-WIND-SECRETARY-001"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _flag(value: Any) -> bool:
    return bool(value)


@dataclass
class SecretaryReport:
    program_id: str
    risk_level: str
    risk_score: int
    predicted_failure_modes: List[str]
    preemptive_actions: List[str]
    owner_ui_actions: List[str]
    evidence_required: List[str]
    should_pre_save: bool
    should_compact: bool
    should_request_same_slot_rebind: bool
    formal_authority_untouched: bool


def assess(snapshot: Dict[str, Any]) -> SecretaryReport:
    continuity = snapshot.get("continuity", {})
    runtime = snapshot.get("runtime", {})
    browser = snapshot.get("browser", {})
    route = snapshot.get("route", {})

    score = 0
    modes: List[str] = []
    actions: List[str] = []
    owner_actions: List[str] = []
    evidence: List[str] = []

    context_load = _num(runtime.get("context_load_factor"), 1.0)
    active = int(_num(runtime.get("active_item_count"), 0))
    stale = int(_num(runtime.get("stale_ref_count"), 0))
    waste = int(_num(runtime.get("waste_count"), 0))
    duplicate_ratio = _num(runtime.get("duplicate_ratio"), 0.0)
    tool_streak = int(_num(runtime.get("tool_failure_streak"), 0))
    web_streak = int(_num(runtime.get("web_failure_streak"), 0))
    long_lived_hours = _num(runtime.get("window_age_hours"), 0.0)

    home_ok = _flag(continuity.get("home_read_ok"))
    mission_ok = _flag(continuity.get("mission_read_ok"))
    backup_ok = _flag(continuity.get("self_backup_read_ok"))
    receipt_ok = _flag(continuity.get("wake_receipt_read_ok"))

    all_pages_unreachable = _flag(browser.get("all_pages_unreachable"))
    ui_frozen = _flag(browser.get("ui_frozen"))
    endless = _flag(browser.get("blank_or_endless_loading"))
    websocket_errors = int(_num(browser.get("websocket_error_count"), 0))
    route_drift = _flag(route.get("route_drift"))
    role_mismatch = _flag(route.get("formal_role_task_mismatch"))

    if not home_ok or not mission_ok:
        score += 55
        modes.append("DURABLE_AUTHORITY_READ_FAILURE")
        evidence.append("fresh Home and MISSION_STATE read result")
    if not backup_ok or not receipt_ok:
        score += 20
        modes.append("RECOVERY_ANCHOR_INCOMPLETE")
        actions.append("SAVE_CHECKPOINT_REQUEST")
    if context_load >= 3:
        score += 15
        modes.append("CONTEXT_PRESSURE_RISING")
    if context_load >= 5:
        score += 20
        modes.append("EXTREME_CONTEXT_PRESSURE")
    if active > 10 or waste >= 20 or stale >= 10 or duplicate_ratio >= 0.35:
        score += 15
        modes.append("METABOLIC_PRESSURE")
        actions.append("LOW_RISK_COMPACTION_REQUEST")
    if stale > 0:
        score += min(15, stale * 2)
        modes.append("STALE_POINTER_RISK")
        actions.append("FRESH_READ_RECONCILIATION_REQUEST")
    if tool_streak >= 3 or web_streak >= 3:
        score += 20
        modes.append("TOOL_OR_WEB_FAILURE_STREAK")
    if route_drift:
        score += 20
        modes.append("ROUTE_DRIFT")
        actions.append("ROUTE_DRIFT_ALERT")
    if role_mismatch:
        score += 20
        modes.append("FORMAL_ROLE_TASK_MISMATCH")
    if ui_frozen or endless:
        score += 20
        modes.append("BROWSER_UI_PRESSURE")
        owner_actions.append("hard refresh or fresh chat after durable save")
    if all_pages_unreachable:
        score += 35
        modes.append("WINDOW_OR_SESSION_TRANSPORT_FAILURE")
        owner_actions.extend([
            "test fresh browser profile or incognito",
            "check status.openai.com",
            "collect timestamp and conversation URL",
        ])
    if websocket_errors > 0:
        score += min(15, websocket_errors * 3)
        modes.append("WEBSOCKET_OR_SESSION_INSTABILITY")
        evidence.append("browser console or HAR if recurrence persists")
    if long_lived_hours >= 8 and context_load >= 3:
        score += 10
        modes.append("LONG_LIVED_WINDOW_PRESSURE")

    score = min(score, 100)
    if score >= 70:
        level = "RED"
    elif score >= 45:
        level = "ORANGE"
    elif score >= 20:
        level = "YELLOW"
    else:
        level = "GREEN"

    should_pre_save = level in {"YELLOW", "ORANGE", "RED"}
    should_compact = (
        level in {"ORANGE", "RED"}
        or active > 10
        or waste >= 20
        or stale >= 10
        or duplicate_ratio >= 0.35
    )
    should_rebind = (
        all_pages_unreachable
        and home_ok
        and mission_ok
        and backup_ok
        and receipt_ok
    ) or role_mismatch

    if should_pre_save and "SAVE_CHECKPOINT_REQUEST" not in actions:
        actions.insert(0, "SAVE_CHECKPOINT_REQUEST")
    if level in {"ORANGE", "RED"}:
        actions.append("OPEN_RECOVERY_CAPSULE")
        actions.append("NAVIGATOR_RISK_ESCALATION")
    if should_rebind:
        actions.append("SAME_SLOT_REBIND_REQUEST")
    if level == "RED":
        actions.append("PAUSE_NEW_NONESSENTIAL_LOAD_UNTIL_RECOVERY_CHECK")

    return SecretaryReport(
        program_id=PROGRAM_ID,
        risk_level=level,
        risk_score=score,
        predicted_failure_modes=sorted(set(modes)),
        preemptive_actions=list(dict.fromkeys(actions)),
        owner_ui_actions=list(dict.fromkeys(owner_actions)),
        evidence_required=list(dict.fromkeys(evidence)),
        should_pre_save=should_pre_save,
        should_compact=should_compact,
        should_request_same_slot_rebind=should_rebind,
        formal_authority_untouched=True,
    )


def report_dict(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return asdict(assess(snapshot))
