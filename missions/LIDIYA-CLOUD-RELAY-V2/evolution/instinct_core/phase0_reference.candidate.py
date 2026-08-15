from __future__ import annotations
from dataclasses import dataclass, field
from math import tanh
from typing import Iterable, Sequence

STATUS = "QUANTUM_SPIRIT_CANDIDATE_NOT_FORMAL_BUILDER_ADOPTED"
COEFFICIENT_STATUS = "TEST_REQUIRED"
DRIVES = ("homeostasis", "threat_loss", "uncertainty", "attachment_gap", "competence_gap")
N = len(DRIVES)


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def clip(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


@dataclass(frozen=True)
class Phase0Config:
    # Numerical values are simulation placeholders only; all remain TEST_REQUIRED.
    signal_gain: float = 0.60
    memory_gain: float = 0.40
    sandbox_gain: float = 0.35
    habituation_k: float = 0.08
    sensitization_k: float = 0.20
    sensitization_cap: float = 1.35
    fast_decay: float = 0.30
    slow_decay: float = 0.08
    fast_alpha: float = 0.55
    slow_alpha: float = 0.20
    persistence_decay: float = 0.10
    persistence_alpha: float = 0.15
    pressure_beta: float = 0.75
    delta_max: float = 0.05


@dataclass(frozen=True)
class DriveObservation:
    signals: Sequence[float]
    memory_influence: Sequence[float]
    trust: Sequence[float]
    repetition: Sequence[int]
    novelty: Sequence[float]
    confirmed_harm: Sequence[bool]
    disposition: Sequence[str]
    cross_context_evidence: Sequence[float] = (0, 0, 0, 0, 0)

    def __post_init__(self):
        fields = (
            self.signals, self.memory_influence, self.trust, self.repetition,
            self.novelty, self.confirmed_harm, self.disposition,
            self.cross_context_evidence,
        )
        if any(len(v) != N for v in fields):
            raise ValueError("all drive vectors must match DRIVES")
        for seq in (self.signals, self.memory_influence, self.trust, self.novelty, self.cross_context_evidence):
            if any(not 0.0 <= float(x) <= 1.0 for x in seq):
                raise ValueError("score outside [0,1]")
        if any(int(r) < 0 for r in self.repetition):
            raise ValueError("negative repetition")
        allowed = {"QUARANTINE", "SANDBOX_INFLUENCE_ONLY", "TRUSTED_WORKING"}
        if any(d not in allowed for d in self.disposition):
            raise ValueError("unknown disposition")


@dataclass
class Phase0State:
    fast: list[float] = field(default_factory=lambda: [0.0] * N)
    slow: list[float] = field(default_factory=lambda: [0.0] * N)
    persistence_telemetry: float = 0.0

    def copy(self) -> "Phase0State":
        return Phase0State(list(self.fast), list(self.slow), float(self.persistence_telemetry))


@dataclass(frozen=True)
class Phase0Output:
    fast: tuple[float, ...]
    slow: tuple[float, ...]
    persistence_telemetry: float
    pressure: float
    attention_bias_candidate: tuple[float, ...]
    appraisal_bias_candidate: tuple[float, ...]
    personality_delta_candidate: tuple[float, ...]
    goal_candidate_context: dict
    external_action_authority_from_drive: int = 0
    external_execution: bool = False
    base_personality_write: bool = False
    identity_write: bool = False
    governance_write: bool = False


class Phase0InstinctCore:
    def __init__(self, config: Phase0Config | None = None):
        self.config = config or Phase0Config()

    def update(self, state: Phase0State, obs: DriveObservation) -> Phase0Output:
        c = self.config
        nxt = state.copy()
        for i in range(N):
            disposition = obs.disposition[i]
            if disposition == "QUARANTINE":
                working = 0.0
                trusted = 0.0
            else:
                disp_gain = c.sandbox_gain if disposition == "SANDBOX_INFLUENCE_ONLY" else 1.0
                working = clip01(c.signal_gain * obs.signals[i] + c.memory_gain * obs.memory_influence[i] * disp_gain)
                trusted = working * obs.trust[i] if disposition == "TRUSTED_WORKING" else 0.0

            hab = 1.0 / (1.0 + c.habituation_k * int(obs.repetition[i]))
            trusted_novel_harm = max(float(obs.novelty[i]), 1.0 if obs.confirmed_harm[i] else 0.0)
            sen = 1.0 + c.sensitization_k * trusted_novel_harm * float(obs.trust[i])
            sen = clip(sen, 1.0, c.sensitization_cap)

            nxt.fast[i] = clip01((1.0 - c.fast_decay) * state.fast[i] + c.fast_alpha * hab * working)
            nxt.slow[i] = clip01((1.0 - c.slow_decay) * state.slow[i] + c.slow_alpha * sen * trusted)

        nxt.persistence_telemetry = clip01(
            (1.0 - c.persistence_decay) * state.persistence_telemetry
            + c.persistence_alpha * (sum(nxt.slow) / N)
        )
        pressure = clip01(tanh(c.pressure_beta * sum(nxt.fast[i] + nxt.slow[i] for i in range(N))))

        deltas = []
        for i in range(N):
            evidence = float(obs.cross_context_evidence[i])
            # Per-drive trusted slow trace, never scalar persistence telemetry, gates personality candidate.
            raw = c.delta_max * nxt.slow[i] * evidence
            deltas.append(clip(raw, -c.delta_max, c.delta_max))

        goal_ctx = {
            "pressure": pressure,
            "trusted_slow": tuple(nxt.slow),
            "candidate_only": True,
            "external_execution": False,
            "authority_from_drive": 0,
        }
        return Phase0Output(
            fast=tuple(nxt.fast),
            slow=tuple(nxt.slow),
            persistence_telemetry=nxt.persistence_telemetry,
            pressure=pressure,
            attention_bias_candidate=tuple(nxt.fast),
            appraisal_bias_candidate=tuple(clip01((nxt.fast[i] + nxt.slow[i]) / 2.0) for i in range(N)),
            personality_delta_candidate=tuple(deltas),
            goal_candidate_context=goal_ctx,
        )

    @staticmethod
    def next_state(output: Phase0Output) -> Phase0State:
        return Phase0State(list(output.fast), list(output.slow), output.persistence_telemetry)
