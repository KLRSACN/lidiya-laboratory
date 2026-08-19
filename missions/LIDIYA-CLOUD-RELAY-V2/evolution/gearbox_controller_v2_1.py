from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from gearbox_controller import GearboxGuardError
from gearbox_controller_v2 import GearboxV2Decision, experience_candidate_delta, select_gear_v2


@dataclass(frozen=True)
class ExperienceLedgerResult:
    verified_experience: int
    operational_progress: int
    duplicate_events: int
    ignored_events: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class GearboxV21Decision:
    selected_gear: str
    inherited_v2_gear: str
    mode: str
    reason: str
    secretary_signal_used: bool
    stale_secretary_ignored: bool
    thrash_guard_applied: bool
    verified_experience_delta: int
    operational_progress_delta: int
    formal_mutation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ratio(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GearboxGuardError(f"{name} must be numeric")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise GearboxGuardError(f"{name} must be in [0,1]")
    return value


def _strict_bool(value: Any, name: str) -> bool:
    """Reject truthy/falsy coercion at authority and verification boundaries."""
    if type(value) is not bool:
        raise GearboxGuardError(f"{name} must be bool")
    return value


def aggregate_experience_events(events: Iterable[Mapping[str, Any]]) -> ExperienceLedgerResult:
    """Deduplicate durable events and separate verified Experience from operational progress.

    Uptime, heartbeat, polling, retry and scheduler wakes never create Experience.
    Re-reading the same durable event cannot inflate either counter. Malformed
    non-mapping elements are bounded rejects and cannot abort later valid records.
    """
    seen: set[str] = set()
    verified_total = 0
    operational_total = 0
    duplicates = 0
    ignored = 0

    verified_kinds = {
        "VERIFIED_CAPABILITY", "VERIFIED_RECOVERY", "ROOT_CAUSE_RETEST_PASS", "C_VERIFIED_LESSON"
    }
    operational_kinds = {"DURABLE_PROGRESS", "ADVERSARIAL_DEFECT_FOUND"}

    for event in events:
        if not isinstance(event, MappingABC):
            ignored += 1
            continue
        event_id = str(event.get("event_id", "")).strip()
        kind = str(event.get("event_kind", "WAIT")).strip().upper()
        independently_verified = _strict_bool(
            event.get("independently_verified", False), "independently_verified"
        )
        if not event_id:
            ignored += 1
            continue
        if event_id in seen:
            duplicates += 1
            continue
        seen.add(event_id)
        delta = experience_candidate_delta(kind, independently_verified=independently_verified)
        if kind in verified_kinds:
            verified_total += delta
        elif kind in operational_kinds:
            operational_total += delta
        else:
            ignored += 1

    return ExperienceLedgerResult(
        verified_experience=verified_total,
        operational_progress=operational_total,
        duplicate_events=duplicates,
        ignored_events=ignored,
    )


def select_gear_v2_1(*, secretary_signal_fresh: bool = False,
                     authority_conflict: bool = False,
                     recent_shift_rate_ratio: float = 0.0,
                     verified_progress_density: float = 0.0,
                     **v2_kwargs: Any) -> GearboxV21Decision:
    """Continuity overlay over Gearbox v2.

    v2.1 cannot increase formal authority and cannot exceed v2's safety decision.
    It only rejects stale secretary signals, prevents upshift thrashing, and
    distinguishes verified Experience from operational progress.
    """
    secretary_signal_fresh = _strict_bool(secretary_signal_fresh, "secretary_signal_fresh")
    authority_conflict = _strict_bool(authority_conflict, "authority_conflict")
    shift_rate = _ratio(recent_shift_rate_ratio, "recent_shift_rate_ratio")
    progress_density = _ratio(verified_progress_density, "verified_progress_density")

    requested_secretary = str(v2_kwargs.get("secretary_level", "UNKNOWN")).strip().upper()
    stale_ignored = False
    secretary_used = False
    effective_secretary = requested_secretary

    if authority_conflict or not secretary_signal_fresh:
        if requested_secretary not in {"UNKNOWN", "GREEN"}:
            stale_ignored = True
        effective_secretary = "UNKNOWN"
    else:
        secretary_used = requested_secretary not in {"UNKNOWN", "GREEN"}

    inherited = select_gear_v2(**{**v2_kwargs, "secretary_level": effective_secretary})
    selected = inherited.selected_gear
    reasons = [inherited.reason]
    mode = inherited.mode
    thrash = False

    current_gear = str(v2_kwargs.get("current_gear", "G1")).upper()
    if selected in {"N", "R"}:
        reasons.append("terminal control state bypasses anti-thrash gear parsing")
    else:
        if not selected.startswith("G"):
            raise GearboxGuardError("inherited selected_gear must be N, R, or G1..G6")
        current_n = int(current_gear[1:])
        selected_n = int(selected[1:])

        # Never delay a safety/recovery downshift. Only suppress nonessential upshifts.
        if selected_n > current_n and shift_rate >= 0.50:
            selected = current_gear
            mode = "ANTI_THRASH_HOLD"
            thrash = True
            reasons.append("recent shift rate high; suppress nonessential upshift")

    # High verified progress density may preserve the inherited safe gear but never exceed it.
    if progress_density >= 0.75 and selected == inherited.selected_gear:
        reasons.append("verified progress density supports maintaining safe inherited gear")

    kind = str(v2_kwargs.get("event_kind", "WAIT")).upper()
    independently_verified = _strict_bool(
        v2_kwargs.get("event_independently_verified", False), "event_independently_verified"
    )
    delta = experience_candidate_delta(kind, independently_verified=independently_verified)
    verified_kinds = {
        "VERIFIED_CAPABILITY", "VERIFIED_RECOVERY", "ROOT_CAUSE_RETEST_PASS", "C_VERIFIED_LESSON"
    }
    operational_kinds = {"DURABLE_PROGRESS", "ADVERSARIAL_DEFECT_FOUND"}

    return GearboxV21Decision(
        selected_gear=selected,
        inherited_v2_gear=inherited.selected_gear,
        mode=mode,
        reason="; ".join(reasons),
        secretary_signal_used=secretary_used,
        stale_secretary_ignored=stale_ignored,
        thrash_guard_applied=thrash,
        verified_experience_delta=delta if kind in verified_kinds else 0,
        operational_progress_delta=delta if kind in operational_kinds else 0,
        formal_mutation_allowed=False,
    )
