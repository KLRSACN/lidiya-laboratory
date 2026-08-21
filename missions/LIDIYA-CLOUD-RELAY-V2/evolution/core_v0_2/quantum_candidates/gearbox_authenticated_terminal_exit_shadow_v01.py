from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping

from gearbox_controller import GearboxGuardError
from gearbox_authority_experience_signer_shadow_v01 import SignerTrustSnapshot, verify_signed_authority
from gearbox_clock_epoch_recovery_shadow_v03 import ClockRecoveryProjection, REENTERED_STATE
from gearbox_authority_projection_shadow_v01 import PINNED_MISSION_STATE_BLOB_SHA

SCHEMA = "0.1-shadow"
ALLOWED_FRESH_FIELDS = frozenset({
    "mission_state_blob_sha", "home_snapshot_id", "goal_id", "goal_payload_hash",
    "authority_decision_id", "requested_control_state",
})
FORBIDDEN_STALE_FIELDS = frozenset({
    "secretary_level", "pressure_inputs", "pressure_history", "anti_thrash_age",
    "terminal_hold_age", "terminal_hold_history", "provider_retry_count",
    "provider_head_history", "clock_retry_count", "clock_epoch_history",
    "recovery_counter", "recovery_duration", "signer_familiarity", "stale_goal_cache",
    "old_goal_cache", "experience_delta", "trauma_delta", "relief_delta",
    "competence_delta", "preference_delta", "personality_delta", "p_base_delta",
})

class TerminalExitGuardError(GearboxGuardError):
    pass

@dataclass(frozen=True)
class TerminalExitProjection:
    state: str
    goal_id: str
    requested_control_state: str
    fresh_authority_decision_id: str
    routing_authority_allowed: bool
    secretary_level: str = "UNKNOWN"
    pressure_state: str = "NEUTRAL"
    anti_thrash_state: str = "RESET"
    terminal_hold_state: str = "CLEARED"
    recovery_state: str = "CLEARED"
    verified_experience_delta: int = 0
    appraisal_delta: int = 0
    drive_delta: int = 0
    exploration_delta: int = 0
    preference_delta: int = 0
    personality_delta: int = 0
    trauma_or_relief_delta: int = 0
    p_base_mutation: bool = False
    formal_mutation_allowed: bool = False

    def cognitive_state(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: d[k] for k in (
            "secretary_level", "pressure_state", "anti_thrash_state", "terminal_hold_state",
            "recovery_state", "verified_experience_delta", "appraisal_delta", "drive_delta",
            "exploration_delta", "preference_delta", "personality_delta",
            "trauma_or_relief_delta", "p_base_mutation",
        )}

def _token(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value.strip()) > 160:
        raise TerminalExitGuardError(f"{name} must be explicit bounded token")
    return value.strip()

def authenticated_terminal_exit(
    *, reentry: ClockRecoveryProjection, exit_payload: Mapping[str, Any],
    signed_authority: Any, signer_trust_snapshot: Any, mission_state_blob_sha: str,
) -> TerminalExitProjection:
    """Resume shadow routing only from fresh allowlisted state under current authority.

    Recovery/pressure/provider/clock/signer history is never accepted as exit input.
    This is non-formal candidate routing only and cannot mutate formal mission state.
    """
    if reentry.state != REENTERED_STATE or reentry.routing_authority_allowed:
        raise TerminalExitGuardError("authenticated non-routing reentry required")
    if reentry.stale_pressure_carryover or reentry.prior_terminal_hold_carryover:
        raise TerminalExitGuardError("reentry contains stale recovery state")
    if mission_state_blob_sha != PINNED_MISSION_STATE_BLOB_SHA:
        raise TerminalExitGuardError("fresh MISSION authority mismatch; rebase required")
    if not isinstance(exit_payload, Mapping):
        raise TerminalExitGuardError("terminal exit payload mapping required")
    keys = set(exit_payload)
    forbidden = keys & FORBIDDEN_STALE_FIELDS
    if forbidden:
        raise TerminalExitGuardError("forbidden stale terminal-exit fields: " + ",".join(sorted(forbidden)))
    unknown = keys - ALLOWED_FRESH_FIELDS
    if unknown:
        raise TerminalExitGuardError("non-allowlisted terminal-exit fields: " + ",".join(sorted(unknown)))
    missing = ALLOWED_FRESH_FIELDS - keys
    if missing:
        raise TerminalExitGuardError("missing fresh terminal-exit fields: " + ",".join(sorted(missing)))
    if exit_payload["mission_state_blob_sha"] != mission_state_blob_sha:
        raise TerminalExitGuardError("terminal exit payload not bound to fresh MISSION")

    trust = SignerTrustSnapshot.verify(signer_trust_snapshot)
    envelope = verify_signed_authority(signed_authority, trust)
    if envelope.mission_state_blob_sha != mission_state_blob_sha:
        raise TerminalExitGuardError("authority not bound to fresh MISSION")
    decision_id = _token(exit_payload["authority_decision_id"], "authority_decision_id")
    if decision_id != envelope.decision_id:
        raise TerminalExitGuardError("terminal exit authority decision mismatch")
    requested = _token(exit_payload["requested_control_state"], "requested_control_state")
    if requested != envelope.selected_state:
        raise TerminalExitGuardError("fresh authority precedence violation")

    return TerminalExitProjection(
        state="AUTHENTICATED_TERMINAL_EXIT_SHADOW", goal_id=_token(exit_payload["goal_id"], "goal_id"),
        requested_control_state=requested, fresh_authority_decision_id=decision_id,
        routing_authority_allowed=True,
    )

def terminal_exit_boundaries() -> dict[str, Any]:
    return {
        "allowlist": sorted(ALLOWED_FRESH_FIELDS),
        "denylist": sorted(FORBIDDEN_STALE_FIELDS),
        "fresh_mission_precedence": True,
        "current_epoch_authority_precedence": True,
        "stale_pressure_history_allowed": False,
        "stale_terminal_hold_allowed": False,
        "stale_goal_cache_allowed": False,
        "recovery_or_signer_familiarity_allowed": False,
        "terminal_exit_counts_as_experience": False,
        "trauma_or_relief_delta": 0,
        "personality_delta": 0,
        "p_base_mutation_allowed": False,
        "formal_mutation_allowed": False,
    }
