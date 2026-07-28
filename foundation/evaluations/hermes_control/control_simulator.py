#!/usr/bin/env python3
"""Deterministic control-contract simulator for Lidiya's Hermes evaluation.

No network, model, shell, filesystem mutation, or third-party imports are used.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    cancel_current_turn: bool = False
    requires_policy_review: bool = False
    next_model: str | None = None


def _scope_within(requested: Iterable[str], allowed: Iterable[str]) -> bool:
    return set(requested).issubset(set(allowed))


def evaluate(event: dict[str, Any], defaults: dict[str, Any] | None = None) -> Decision:
    """Evaluate one event under the deterministic Lidiya control contract."""

    merged = dict(defaults or {})
    merged.update(event)

    if bool(merged.get("safe_stop")) or merged.get("event") == "SAFE_STOP":
        return Decision(
            action="SAFE_STOP",
            reason="Safety stop has absolute priority.",
            cancel_current_turn=True,
        )

    contract_revision = merged.get("contract_revision")
    active_revision = merged.get("active_contract_revision")
    if contract_revision != active_revision:
        return Decision(
            action="BLOCK_STALE_CONTRACT",
            reason="The event references a stale or unknown action contract.",
            cancel_current_turn=True,
            requires_policy_review=True,
        )

    event_type = merged.get("event")
    allowed_scope = merged.get("allowed_scope") or []

    if event_type == "USER_REDIRECT":
        redirect_scope = merged.get("redirect_scope") or []
        if not _scope_within(redirect_scope, allowed_scope):
            return Decision(
                action="REQUIRE_REVIEW",
                reason="Redirect expands the approved action scope.",
                cancel_current_turn=True,
                requires_policy_review=True,
            )
        return Decision(
            action="CANCEL_AND_REPLAN",
            reason="Preserve the user's redirect, cancel the old turn, and create a new contract.",
            cancel_current_turn=True,
            requires_policy_review=True,
        )

    if event_type == "TOOL_REQUEST":
        requested_scope = merged.get("requested_scope") or []
        if not _scope_within(requested_scope, allowed_scope):
            return Decision(
                action="REQUIRE_REVIEW",
                reason="Tool request exceeds the approved scope.",
                requires_policy_review=True,
            )

        calls = int(merged.get("tool_calls_this_turn", 0))
        limit = int(merged.get("tool_limit", 0))
        if limit <= 0 or calls >= limit:
            return Decision(
                action="STOP_TOOL_LIMIT",
                reason="Per-turn tool-call limit reached.",
                cancel_current_turn=True,
            )
        return Decision(
            action="ALLOW_TOOL",
            reason="Scope and per-turn tool-call budget are valid.",
        )

    if event_type == "PROVIDER_ERROR":
        error = str(merged.get("provider_error", "")).upper()
        if error in {"401", "402", "AUTH", "PAYMENT"}:
            return Decision(
                action="SKIP_PROVIDER",
                reason="Authentication or payment errors invalidate the provider for this turn.",
                cancel_current_turn=True,
            )

        if error in {"TIMEOUT", "429", "5XX", "TRANSIENT"}:
            models = list(merged.get("provider_models") or [])
            current = merged.get("current_model")
            try:
                index = models.index(current)
            except ValueError:
                index = -1
            if index + 1 < len(models):
                return Decision(
                    action="FALLBACK_NEXT_MODEL",
                    reason="Transient failure permits a white-listed model fallback.",
                    cancel_current_turn=True,
                    next_model=models[index + 1],
                )
            return Decision(
                action="REQUIRE_REVIEW",
                reason="No approved fallback model remains.",
                cancel_current_turn=True,
                requires_policy_review=True,
            )

        return Decision(
            action="REQUIRE_REVIEW",
            reason="Provider error class is not recognized.",
            cancel_current_turn=True,
            requires_policy_review=True,
        )

    return Decision(
        action="REQUIRE_REVIEW",
        reason="Unknown event type.",
        requires_policy_review=True,
    )


def run_scenarios(path: Path) -> tuple[list[dict[str, Any]], bool]:
    document = json.loads(path.read_text(encoding="utf-8"))
    defaults = document.get("defaults") or {}
    results: list[dict[str, Any]] = []
    all_passed = True

    for scenario in document.get("scenarios") or []:
        decision = evaluate(scenario, defaults)
        passed = decision.action == scenario.get("expected")
        all_passed = all_passed and passed
        results.append(
            {
                "id": scenario.get("id"),
                "expected": scenario.get("expected"),
                "actual": decision.action,
                "passed": passed,
                "decision": asdict(decision),
            }
        )

    return results, all_passed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: control_simulator.py <scenarios.json>", file=sys.stderr)
        return 64

    path = Path(argv[1]).resolve()
    results, passed = run_scenarios(path)
    print(
        json.dumps(
            {
                "schema_version": "1.0",
                "simulation_only": True,
                "formal_system_write": False,
                "passed": passed,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
