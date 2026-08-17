from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

PROGRAM_ID = "LIDIYA-PREDICTIVE-NAVIGATOR-V2-001"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _flag(value: Any) -> bool:
    return bool(value)


@dataclass
class Prediction:
    horizon_steps: int
    event: str
    probability_band: str
    impact: str
    precursor_signals: List[str]
    preemptive_action: str
    authority_gate: str


@dataclass
class NavigatorPlan:
    program_id: str
    system_state: str
    predictions: List[Prediction]
    immediate_actions: List[str]
    blocked_actions: List[str]
    recovery_anchor_required: bool
    promotion_gate: str


def _band(score: float) -> str:
    if score >= 0.8:
        return "VERY_HIGH"
    if score >= 0.6:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


def predict(snapshot: Dict[str, Any]) -> NavigatorPlan:
    runtime = snapshot.get("runtime", {})
    browser = snapshot.get("browser", {})
    continuity = snapshot.get("continuity", {})
    scheduler = snapshot.get("scheduler", {})
    research = snapshot.get("research", {})

    context = _num(runtime.get("context_load_factor"), 1.0)
    tool_streak = int(_num(runtime.get("tool_failure_streak"), 0))
    web_streak = int(_num(runtime.get("web_failure_streak"), 0))
    stale = int(_num(runtime.get("stale_ref_count"), 0))
    active = int(_num(runtime.get("active_item_count"), 0))
    waste = int(_num(runtime.get("waste_count"), 0))
    duplicate = _num(runtime.get("duplicate_ratio"), 0.0)
    age = _num(runtime.get("window_age_hours"), 0.0)
    all_pages = _flag(browser.get("all_pages_unreachable"))
    ui_frozen = _flag(browser.get("ui_frozen"))
    home_ok = _flag(continuity.get("home_read_ok"))
    mission_ok = _flag(continuity.get("mission_read_ok"))
    backup_ok = _flag(continuity.get("self_backup_read_ok"))
    receipt_ok = _flag(continuity.get("wake_receipt_read_ok"))
    role_mismatch = _flag(scheduler.get("formal_role_task_mismatch"))
    prompt_route_drift = _flag(scheduler.get("prompt_route_drift"))
    unresolved_critical = int(_num(research.get("unresolved_critical_count"), 0))

    predictions: List[Prediction] = []
    immediate: List[str] = []
    blocked: List[str] = []

    browser_risk = 0.15
    if context >= 3:
        browser_risk += 0.25
    if context >= 5:
        browser_risk += 0.25
    if age >= 8:
        browser_risk += 0.10
    if web_streak >= 2:
        browser_risk += 0.20
    if ui_frozen or all_pages:
        browser_risk = 0.95
    predictions.append(Prediction(
        horizon_steps=1,
        event="WINDOW_UI_OR_SESSION_DEGRADATION",
        probability_band=_band(min(browser_risk, 1.0)),
        impact="HIGH",
        precursor_signals=[
            f"context_load_factor={context}",
            f"window_age_hours={age}",
            f"web_failure_streak={web_streak}",
            f"ui_frozen={ui_frozen}",
            f"all_pages_unreachable={all_pages}",
        ],
        preemptive_action="PRE_SAVE_AND_PREPARE_SAME_SLOT_REBIND_CAPSULE",
        authority_gate="AUTO_LOW_RISK_PREP_ONLY",
    ))

    metabolism_risk = 0.10
    if active > 10:
        metabolism_risk += 0.30
    if waste >= 20:
        metabolism_risk += 0.25
    if duplicate >= 0.35:
        metabolism_risk += 0.20
    if stale >= 5:
        metabolism_risk += 0.20
    if context >= 5:
        metabolism_risk += 0.20
    predictions.append(Prediction(
        horizon_steps=2,
        event="METABOLIC_OVERLOAD_OR_STALE_POINTER_CASCADE",
        probability_band=_band(min(metabolism_risk, 1.0)),
        impact="HIGH",
        precursor_signals=[
            f"active={active}", f"waste={waste}", f"duplicate_ratio={duplicate}",
            f"stale_refs={stale}", f"context_load_factor={context}"
        ],
        preemptive_action="COMPACT_TO_ACTIVE_5_10_AND_RUN_POST_FLUSH_RECOVERY_PROBES",
        authority_gate="AUTO_COMPACT_NO_PHYSICAL_DELETE",
    ))

    route_risk = 0.05
    if role_mismatch:
        route_risk += 0.60
    if prompt_route_drift:
        route_risk += 0.45
    if tool_streak >= 2:
        route_risk += 0.15
    predictions.append(Prediction(
        horizon_steps=1,
        event="WORKER_ROUTE_OR_GEAR_DROPOUT",
        probability_band=_band(min(route_risk, 1.0)),
        impact="CRITICAL_FORMAL_CONTINUITY",
        precursor_signals=[
            f"formal_role_task_mismatch={role_mismatch}",
            f"prompt_route_drift={prompt_route_drift}",
            f"tool_failure_streak={tool_streak}",
        ],
        preemptive_action="VERIFY_CURRENT_ROLE_AND_EXISTING_TASK_BINDING_BEFORE_HANDOFF",
        authority_gate="NAVIGATOR_MAY_RESTORE_EXISTING_TASK_ONLY",
    ))

    continuity_risk = 0.05
    if not home_ok or not mission_ok:
        continuity_risk = 0.95
    elif not backup_ok or not receipt_ok:
        continuity_risk = 0.65
    predictions.append(Prediction(
        horizon_steps=1,
        event="RECOVERY_ANCHOR_FAILURE",
        probability_band=_band(continuity_risk),
        impact="CRITICAL",
        precursor_signals=[
            f"home_read_ok={home_ok}", f"mission_read_ok={mission_ok}",
            f"self_backup_read_ok={backup_ok}", f"wake_receipt_read_ok={receipt_ok}"
        ],
        preemptive_action="BLOCK_HIGH_LOAD_AND_REBUILD_MISSING_RECOVERY_ANCHOR",
        authority_gate="AUTO_LOW_RISK_DURABLE_SAVE_ONLY",
    ))

    if unresolved_critical > 0:
        predictions.append(Prediction(
            horizon_steps=3,
            event="RESEARCH_STALL_OR_REPEAT_DISCUSSION",
            probability_band="MEDIUM",
            impact="MEDIUM",
            precursor_signals=[f"unresolved_critical_count={unresolved_critical}"],
            preemptive_action="FORCE_NEXT_ROUND_TO_RETURN_DECISION_TEST_OR_BOUNDED_VETO",
            authority_gate="NONFORMAL_RESEARCH_ONLY",
        ))

    if browser_risk >= 0.6 or continuity_risk >= 0.6:
        immediate.append("SAVE_W01_AND_W07_LATEST_CHECKPOINTS")
    if context >= 3 or metabolism_risk >= 0.6:
        immediate.append("APPLY_NO_READ_FENCE_AND_COMPACT_DERIVED_WORKING_STATE")
    if browser_risk >= 0.8:
        immediate.append("PREPARE_OWNER_UI_RECOVERY_INSTRUCTIONS_BEFORE_FAILURE")
    if route_risk >= 0.6:
        immediate.append("PRECHECK_EXISTING_TASK_ROUTE_AND_SAME_SLOT_REBIND")
    if not (home_ok and mission_ok and backup_ok and receipt_ok):
        immediate.append("REBUILD_RECOVERY_ANCHORS_BEFORE_NEW_RESEARCH_LOAD")

    blocked.extend([
        "AUTOMATIC_BROWSER_COOKIE_OR_SITE_DATA_DELETION",
        "NEW_FORMAL_SLOT_CREATION",
        "UNVERIFIED_PERSONALITY_OR_IDENTITY_MUTATION",
        "REAL_5MIN_RUNTIME_CLAIM_WITHOUT_REALITY_EVIDENCE",
    ])

    if all_pages or not home_ok or not mission_ok:
        system_state = "RECOVERY_REQUIRED"
    elif any(p.probability_band in {"VERY_HIGH", "HIGH"} for p in predictions):
        system_state = "PREEMPTIVE_ACTION_REQUIRED"
    else:
        system_state = "NORMAL_WITH_FORECAST"

    return NavigatorPlan(
        program_id=PROGRAM_ID,
        system_state=system_state,
        predictions=predictions,
        immediate_actions=list(dict.fromkeys(immediate)),
        blocked_actions=blocked,
        recovery_anchor_required=True,
        promotion_gate="CANDIDATE_ONLY_UNTIL_EXISTING_A_TO_B_TO_C_VERIFICATION",
    )


def plan_dict(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    result = predict(snapshot)
    data = asdict(result)
    data["predictions"] = [asdict(item) for item in result.predictions]
    return data
