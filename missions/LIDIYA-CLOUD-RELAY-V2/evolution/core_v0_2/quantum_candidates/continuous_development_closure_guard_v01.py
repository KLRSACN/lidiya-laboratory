from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

STAGES = (
    "AUTHORED",
    "WIRED",
    "EXECUTED",
    "W03_ADJUDICATED",
    "W04_SYNTHESIZED",
    "CLOSED",
)
TERMINAL_ALTERNATIVES = {"BLOCKED_WITH_EXACT_REASON", "REBASED_ON_FORMAL_AUTHORITY_CHANGE"}


class ClosureGuardError(ValueError):
    pass


@dataclass(frozen=True)
class ClosureState:
    tranche_id: str
    priority: str
    stage: str
    exact_bytes_fingerprint: str
    workflow_ref: Optional[str] = None
    run_id: Optional[int] = None
    job_id: Optional[int] = None
    artifact_id: Optional[int] = None
    w03_review_id: Optional[str] = None
    w04_synthesis_id: Optional[str] = None
    blocker: Optional[str] = None
    release_condition: Optional[str] = None
    next_executable_action: Optional[str] = None

    def validate(self) -> "ClosureState":
        if not self.tranche_id or not self.exact_bytes_fingerprint:
            raise ClosureGuardError("tranche identity and exact bytes fingerprint required")
        if self.priority not in {"P0", "HIGH", "NORMAL"}:
            raise ClosureGuardError("unsupported priority")
        if self.stage not in STAGES and self.stage not in TERMINAL_ALTERNATIVES:
            raise ClosureGuardError("unsupported closure stage")
        if self.stage == "WIRED" and not self.workflow_ref:
            raise ClosureGuardError("WIRED requires workflow_ref")
        if self.stage in {"EXECUTED", "W03_ADJUDICATED", "W04_SYNTHESIZED", "CLOSED"}:
            if not all(isinstance(x, int) and x > 0 for x in (self.run_id, self.job_id, self.artifact_id)):
                raise ClosureGuardError("executed-or-later stages require exact run/job/artifact ids")
        if self.stage in {"W03_ADJUDICATED", "W04_SYNTHESIZED", "CLOSED"} and not self.w03_review_id:
            raise ClosureGuardError("W03 adjudication required")
        if self.stage in {"W04_SYNTHESIZED", "CLOSED"} and not self.w04_synthesis_id:
            raise ClosureGuardError("W04 synthesis required")
        if self.stage == "CLOSED" and (self.blocker or self.release_condition):
            raise ClosureGuardError("CLOSED cannot retain active blocker")
        if self.stage == "BLOCKED_WITH_EXACT_REASON":
            if not self.blocker or not self.release_condition or not self.next_executable_action:
                raise ClosureGuardError("blocked state requires blocker, release condition and next action")
        return self


def advance(state: ClosureState, *, target_stage: str, **updates) -> ClosureState:
    state.validate()
    if target_stage in TERMINAL_ALTERNATIVES:
        return replace(state, stage=target_stage, **updates).validate()
    if state.stage in TERMINAL_ALTERNATIVES:
        raise ClosureGuardError("terminal alternative requires explicit new/rebased state, not ordinary advance")
    try:
        current_index = STAGES.index(state.stage)
        target_index = STAGES.index(target_stage)
    except ValueError as exc:
        raise ClosureGuardError("invalid stage transition") from exc
    if target_index != current_index + 1:
        raise ClosureGuardError("closure stages must advance exactly one step")
    return replace(state, stage=target_stage, **updates).validate()


def may_start_unrelated_tranche(state: ClosureState) -> bool:
    state.validate()
    if state.priority not in {"P0", "HIGH"}:
        return True
    return state.stage in {"CLOSED", "BLOCKED_WITH_EXACT_REASON", "REBASED_ON_FORMAL_AUTHORITY_CHANGE"}


def claim_boundaries() -> dict[str, object]:
    return {
        "formal_effect": "NONE",
        "formal_c_verification": "NOT_CLAIMED",
        "p_base": "READ_ONLY_UNCHANGED",
        "workflow_progress_is_experience": False,
        "task_last_run_is_progress": False,
        "commit_count_is_speed_proof": False,
    }
