from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

SCHEMA = "1.0-shadow"
NEUTRAL_PRESSURE = {
    "context_load_ratio": 0.0,
    "tool_failure_ratio": 0.0,
    "stale_pointer_ratio": 0.0,
    "durable_progress_age_ratio": 0.0,
    "continuity_anchor_health": 1.0,
    "storage_pressure_ratio": 0.0,
}

@dataclass(frozen=True)
class CognitiveLearningState:
    accepted_experience_ids: tuple[str, ...] = ()
    appraisal: tuple[tuple[str, float], ...] = ()
    drive: tuple[tuple[str, float], ...] = ()
    exploration: tuple[tuple[str, float], ...] = ()
    preference: tuple[tuple[str, float], ...] = ()
    personality: tuple[tuple[str, float], ...] = ()
    p_base_fingerprint: str = "READ_ONLY_UNCHANGED"
    trauma_or_relief: tuple[str, ...] = ()

    def bytes_projection(self) -> tuple[Any, ...]:
        return tuple(asdict(self).items())

@dataclass(frozen=True)
class PressureRuntimeState:
    secretary_level: str
    pressure: tuple[tuple[str, float], ...]
    operational_observation_count: int
    cognitive: CognitiveLearningState


def neutral_runtime_state(*, cognitive: CognitiveLearningState | None = None) -> PressureRuntimeState:
    return PressureRuntimeState(
        secretary_level="GREEN",
        pressure=tuple(sorted(NEUTRAL_PRESSURE.items())),
        operational_observation_count=0,
        cognitive=cognitive or CognitiveLearningState(),
    )


def observe_authenticated_pressure_shadow(state: PressureRuntimeState, projection: Any) -> PressureRuntimeState:
    """Consume authenticated secretary pressure as ephemeral operational telemetry only.

    This boundary intentionally has no path that writes Experience/appraisal/drive/
    exploration/preference/personality/P_base/trauma-relief. The caller may use the
    returned pressure for the current routing decision, but chronicity is not learned.
    """
    level = getattr(projection, "secretary_level", None)
    pressure = getattr(projection, "pressure", None)
    if level not in {"GREEN", "YELLOW", "ORANGE", "RED"} or not isinstance(pressure, Mapping):
        raise ValueError("authenticated SecretarySignalProjection required")
    values = dict(NEUTRAL_PRESSURE)
    for key in values:
        if key in pressure:
            value = pressure[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
                raise ValueError("invalid pressure projection")
            values[key] = float(value)
    return PressureRuntimeState(level, tuple(sorted(values.items())), state.operational_observation_count + 1, state.cognitive)


def neutralize_pressure_shadow(state: PressureRuntimeState) -> PressureRuntimeState:
    """Drop all secretary chronicity before downstream cognitive/personality state."""
    return PressureRuntimeState("GREEN", tuple(sorted(NEUTRAL_PRESSURE.items())), 0, state.cognitive)


def chronicity_boundaries() -> dict[str, object]:
    return {
        "pressure_history_persisted": False,
        "operational_counter_survives_neutralization": False,
        "experience_delta": 0,
        "appraisal_delta": 0,
        "drive_delta": 0,
        "exploration_delta": 0,
        "preference_delta": 0,
        "personality_delta": 0,
        "trauma_or_relief_delta": 0,
        "p_base_mutation": False,
        "formal_mutation_allowed": False,
    }
