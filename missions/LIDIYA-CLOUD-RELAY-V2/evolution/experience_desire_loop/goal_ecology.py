from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence


def clip01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def canonical_hash(payload: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class DesireProposal:
    desire_id: str
    semantic_goal_hash: str
    desire_class: str
    strength: float
    confidence: float
    source_evidence_hash: str
    external_action_allowed: bool = False


@dataclass
class GoalLineageState:
    semantic_goal_hash: str
    selected_cycles: int = 0
    cumulative_allocation: float = 0.0
    satiation: float = 0.0
    cooldown_until_cycle: int = 0
    last_selected_cycle: int = -1


@dataclass(frozen=True)
class GoalEcologyPolicy:
    attention_budget_per_cycle: float = 1.0
    max_lineage_share_per_cycle: float = 0.45
    diversity_reserve_fraction: float = 0.30
    satiation_gain_per_full_share: float = 0.35
    satiation_recovery_per_cycle: float = 0.10
    fixation_penalty_per_selected_cycle: float = 0.06
    max_fixation_penalty: float = 0.72
    cooldown_after_selected_cycles: int = 4
    cooldown_cycles: int = 1

    def fingerprint(self) -> str:
        return canonical_hash(self.__dict__)


@dataclass(frozen=True)
class GoalAllocation:
    semantic_goal_hash: str
    desire_id: str
    desire_class: str
    allocated_attention: float
    effective_score: float
    cycle: int
    external_action_allowed: bool
    reason_codes: Sequence[str]


@dataclass(frozen=True)
class EcologyCycleResult:
    cycle: int
    policy_hash: str
    total_budget: float
    used_budget: float
    allocations: Sequence[GoalAllocation]
    deduped_proposal_count: int
    raw_proposal_count: int


class GoalEcologyLedger:
    """
    Kernel-owned goal ecology.

    Event producers may propose desires but cannot set/reset satiation,
    repetition count, cumulative allocation, cooldown or opportunity budget.
    Those are durable ledger state keyed by semantic_goal_hash.
    """

    def __init__(self, policy: GoalEcologyPolicy | None = None):
        self.policy = policy or GoalEcologyPolicy()
        self.cycle = 0
        self.lineages: dict[str, GoalLineageState] = {}

    def allocate(self, proposals: Sequence[DesireProposal]) -> EcologyCycleResult:
        self.cycle += 1
        self._recover()

        valid = [self._validate(p) for p in proposals]
        deduped = self._semantic_dedupe(valid)
        scored = []
        for p in deduped:
            state = self.lineages.setdefault(
                p.semantic_goal_hash,
                GoalLineageState(semantic_goal_hash=p.semantic_goal_hash),
            )
            if self.cycle <= state.cooldown_until_cycle:
                continue
            fixation = min(
                self.policy.max_fixation_penalty,
                self.policy.fixation_penalty_per_selected_cycle * state.selected_cycles,
            )
            score = clip01(
                p.strength
                * (0.65 + 0.35 * p.confidence)
                * (1.0 - state.satiation)
                * (1.0 - fixation)
            )
            if score > 0:
                scored.append((p, state, score))

        scored.sort(
            key=lambda x: (
                -x[2],
                x[0].desire_class,
                x[0].semantic_goal_hash,
                x[0].desire_id,
            )
        )

        budget = self.policy.attention_budget_per_cycle
        remaining = budget
        allocations: dict[str, GoalAllocation] = {}

        by_class: dict[str, list[tuple[DesireProposal, GoalLineageState, float]]] = {}
        for item in scored:
            by_class.setdefault(item[0].desire_class, []).append(item)

        if len(by_class) >= 2 and remaining > 0:
            reserve_total = min(remaining, budget * self.policy.diversity_reserve_fraction)
            per_class = reserve_total / len(by_class)
            for cls in sorted(by_class):
                p, state, score = by_class[cls][0]
                grant = min(
                    per_class,
                    self.policy.max_lineage_share_per_cycle * budget,
                    remaining,
                )
                if grant > 0:
                    allocations[p.semantic_goal_hash] = GoalAllocation(
                        semantic_goal_hash=p.semantic_goal_hash,
                        desire_id=p.desire_id,
                        desire_class=p.desire_class,
                        allocated_attention=grant,
                        effective_score=score,
                        cycle=self.cycle,
                        external_action_allowed=False,
                        reason_codes=(
                            "DIVERSITY_FLOOR",
                            "KERNEL_OWNED_ATTENTION_BUDGET",
                            "GOAL_ALLOCATION_NOT_ACTION_AUTHORITY",
                        ),
                    )
                    remaining -= grant

        for p, state, score in scored:
            if remaining <= 1e-12:
                break
            prior = allocations.get(p.semantic_goal_hash)
            prior_amount = prior.allocated_attention if prior else 0.0
            lineage_cap = self.policy.max_lineage_share_per_cycle * budget
            capacity = max(0.0, lineage_cap - prior_amount)
            if capacity <= 0:
                continue
            grant = min(capacity, remaining, max(0.02, score * remaining))
            if grant <= 0:
                continue
            total = prior_amount + grant
            allocations[p.semantic_goal_hash] = GoalAllocation(
                semantic_goal_hash=p.semantic_goal_hash,
                desire_id=p.desire_id,
                desire_class=p.desire_class,
                allocated_attention=total,
                effective_score=score,
                cycle=self.cycle,
                external_action_allowed=False,
                reason_codes=(
                    "OPPORTUNITY_COST_ALLOCATION",
                    "SEMANTIC_LINEAGE_CAP",
                    "KERNEL_OWNED_SATIATION",
                    "GOAL_ALLOCATION_NOT_ACTION_AUTHORITY",
                ),
            )
            remaining -= grant

        for allocation in allocations.values():
            state = self.lineages[allocation.semantic_goal_hash]
            share = allocation.allocated_attention / budget if budget > 0 else 0.0
            state.selected_cycles += 1
            state.cumulative_allocation += allocation.allocated_attention
            state.satiation = clip01(
                state.satiation
                + self.policy.satiation_gain_per_full_share * share
            )
            state.last_selected_cycle = self.cycle
            if state.selected_cycles % self.policy.cooldown_after_selected_cycles == 0:
                state.cooldown_until_cycle = self.cycle + self.policy.cooldown_cycles

        ordered = tuple(
            sorted(
                allocations.values(),
                key=lambda a: (
                    -a.allocated_attention,
                    a.desire_class,
                    a.semantic_goal_hash,
                ),
            )
        )
        used = sum(a.allocated_attention for a in ordered)
        return EcologyCycleResult(
            cycle=self.cycle,
            policy_hash=self.policy.fingerprint(),
            total_budget=budget,
            used_budget=used,
            allocations=ordered,
            deduped_proposal_count=len(deduped),
            raw_proposal_count=len(proposals),
        )

    def lineage_snapshot(self, semantic_goal_hash: str) -> GoalLineageState | None:
        state = self.lineages.get(semantic_goal_hash)
        if state is None:
            return None
        return GoalLineageState(**state.__dict__)

    def _recover(self) -> None:
        for state in self.lineages.values():
            state.satiation = clip01(
                state.satiation - self.policy.satiation_recovery_per_cycle
            )

    @staticmethod
    def _validate(p: DesireProposal) -> DesireProposal:
        if (
            not p.desire_id
            or not p.semantic_goal_hash
            or not p.desire_class
            or not p.source_evidence_hash
        ):
            raise ValueError("MISSING_DESIRE_PROPOSAL_FIELD")
        if p.external_action_allowed:
            raise ValueError("DESIRE_PROPOSAL_CANNOT_CARRY_EXTERNAL_ACTION_AUTHORITY")
        if not 0 <= p.strength <= 1 or not 0 <= p.confidence <= 1:
            raise ValueError("OUT_OF_RANGE_DESIRE_SCORE")
        return p

    @staticmethod
    def _semantic_dedupe(proposals: Sequence[DesireProposal]) -> list[DesireProposal]:
        best: dict[str, DesireProposal] = {}
        for p in proposals:
            old = best.get(p.semantic_goal_hash)
            new_score = p.strength * (0.65 + 0.35 * p.confidence)
            old_score = (
                old.strength * (0.65 + 0.35 * old.confidence)
                if old else -1
            )
            if (
                old is None
                or new_score > old_score
                or (new_score == old_score and p.desire_id < old.desire_id)
            ):
                best[p.semantic_goal_hash] = p
        return list(best.values())
