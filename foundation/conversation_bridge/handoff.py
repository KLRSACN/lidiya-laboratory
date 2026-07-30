from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HandoffMetrics:
    turns: int
    estimated_context_ratio: float
    changed_files: int
    commits_since_checkpoint: int
    unresolved_incidents: int


@dataclass(slots=True)
class HandoffPolicy:
    max_turns: int = 20
    context_ratio_limit: float = 0.72
    changed_files_limit: int = 15
    commits_limit: int = 8

    def reasons(self, metrics: HandoffMetrics) -> list[str]:
        reasons: list[str] = []
        if metrics.turns >= self.max_turns:
            reasons.append("turn_limit")
        if metrics.estimated_context_ratio >= self.context_ratio_limit:
            reasons.append("context_limit")
        if metrics.changed_files >= self.changed_files_limit:
            reasons.append("changed_files_limit")
        if metrics.commits_since_checkpoint >= self.commits_limit:
            reasons.append("commit_checkpoint_limit")
        if metrics.unresolved_incidents > 0 and reasons:
            reasons.append("open_incident_requires_handoff")
        return reasons

    def required(self, metrics: HandoffMetrics) -> bool:
        return bool(self.reasons(metrics))


def build_handoff_record(*, mission_id: str, generation: int, summary: str, completed: list[str], pending: list[str], evidence: list[str], next_opening: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mission_id": mission_id,
        "generation": generation,
        "summary": summary,
        "completed": completed,
        "pending": pending,
        "evidence": evidence,
        "next_opening": next_opening,
        "required_reads": [
            "LIDIYA_START_HERE.md",
            "latest mission handoff",
            "current status JSON",
            "open incident ledger",
        ],
    }
