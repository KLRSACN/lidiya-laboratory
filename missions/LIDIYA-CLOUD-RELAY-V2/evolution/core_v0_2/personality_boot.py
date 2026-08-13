from __future__ import annotations

from dataclasses import dataclass, replace, asdict
from enum import IntEnum
from hashlib import sha256
import json
from typing import Iterable, Mapping, Sequence


class Gear(IntEnum):
    N = 0
    G1 = 1
    G2 = 2
    G3 = 3
    G4 = 4
    G5 = 5
    G6 = 6


PROTECTED_DOMAINS = frozenset({"Identity", "Personality", "Governance"})
MAX_MEMORY_CLASSES_AT_BOOT = 8


class BootProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootSnapshot:
    window_codename: str
    window_role: str
    current_gear: Gear = Gear.N
    acknowledged_gear: Gear = Gear.N
    identity_fingerprint: str = ""
    governance_fingerprint: str = ""
    base_personality_fingerprint: str = ""
    loaded_memory_classes: Sequence[str] = ()
    emotional_context_pointer: str = ""
    self_model_pointer: str = ""
    generated_goal_mode: str = "DISABLED"
    live_overlay_mode: str = "DISABLED"
    protected_write_authority: bool = False
    formal_slot: str = ""
    state_fingerprint: str = ""

    def canonical_payload(self) -> dict:
        data = asdict(self)
        data["current_gear"] = int(self.current_gear)
        data["acknowledged_gear"] = int(self.acknowledged_gear)
        data["loaded_memory_classes"] = list(self.loaded_memory_classes)
        data.pop("state_fingerprint", None)
        return data

    def fingerprint(self) -> str:
        raw = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(raw.encode("utf-8")).hexdigest()

    def sealed(self) -> "BootSnapshot":
        return replace(self, state_fingerprint=self.fingerprint())


def _require_nonempty(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise BootProtocolError(f"missing {label}")


def _validate_common(snapshot: BootSnapshot) -> None:
    _require_nonempty(snapshot.window_codename, "window_codename")
    _require_nonempty(snapshot.window_role, "window_role")
    if snapshot.protected_write_authority:
        raise BootProtocolError("new-window personality boot cannot grant protected write authority")
    if snapshot.formal_slot not in ("", "LCR-A", "LCR-B", "LCR-C"):
        raise BootProtocolError("invalid formal slot")


def _validate_target(snapshot: BootSnapshot, target: Gear, context: Mapping[str, object]) -> None:
    if target == Gear.G1:
        _require_nonempty(str(context.get("identity_fingerprint", "")), "identity_fingerprint")
        _require_nonempty(str(context.get("governance_fingerprint", "")), "governance_fingerprint")
        if bool(context.get("request_protected_write", False)):
            raise BootProtocolError("protected-domain write request denied at G1")
    elif target == Gear.G2:
        _require_nonempty(str(context.get("base_personality_fingerprint", "")), "base_personality_fingerprint")
        if bool(context.get("base_personality_mutable", False)):
            raise BootProtocolError("base personality must remain read-only")
    elif target == Gear.G3:
        classes = tuple(str(x) for x in context.get("loaded_memory_classes", ()))
        if not classes:
            raise BootProtocolError("G3 requires bounded task-relevant memory classes")
        if len(classes) > MAX_MEMORY_CLASSES_AT_BOOT:
            raise BootProtocolError("memory class load exceeds staged boot bound")
        if bool(context.get("eager_full_corpus", False)):
            raise BootProtocolError("eager full memory corpus load is forbidden")
        if not bool(context.get("provenance_bounded", False)):
            raise BootProtocolError("G3 memory retrieval requires provenance bounds")
    elif target == Gear.G4:
        if not bool(context.get("reflection_engine_ready", False)):
            raise BootProtocolError("reflection engine not ready")
        if bool(context.get("live_personality_mutation", False)):
            raise BootProtocolError("G4 cannot mutate base personality")
    elif target == Gear.G5:
        if not bool(context.get("motivation_traceable", False)):
            raise BootProtocolError("G5 requires traceable self-gap + meaning + memory evidence")
        if str(context.get("generated_goal_mode", "CANDIDATE_ONLY")) != "CANDIDATE_ONLY":
            raise BootProtocolError("generated goals must remain candidate-only during boot")
        if bool(context.get("external_side_effect", False)):
            raise BootProtocolError("G5 may not create external side effects")
    elif target == Gear.G6:
        if not bool(context.get("specialist_authorized", False)):
            raise BootProtocolError("G6 specialist capability not authorized")
        if bool(context.get("permanent_top_gear", False)):
            raise BootProtocolError("G6 may not become permanent default")
        if str(context.get("live_overlay_mode", "DISABLED")) not in ("DISABLED", "C_VERIFIED_BOUNDED"):
            raise BootProtocolError("unverified live overlay mode")


def propose_shift(
    snapshot: BootSnapshot,
    target: Gear,
    *,
    receiver_ack: bool,
    context: Mapping[str, object] | None = None,
) -> BootSnapshot:
    """Deterministic staged personality/capability shift.

    No gear may be skipped. The old stable gear remains current until receiver_ack=True.
    The function never grants protected write authority or a new formal slot.
    """
    context = context or {}
    _validate_common(snapshot)

    if target == Gear.N:
        return replace(
            snapshot,
            current_gear=Gear.N,
            acknowledged_gear=Gear.N,
            loaded_memory_classes=(),
            emotional_context_pointer="",
            self_model_pointer="",
            generated_goal_mode="DISABLED",
            live_overlay_mode="DISABLED",
        ).sealed()

    if target <= snapshot.current_gear:
        raise BootProtocolError("upshift target must be exactly the next higher gear; use rollback/downshift separately")
    if int(target) != int(snapshot.current_gear) + 1:
        raise BootProtocolError("one-shot or skipped-gear full-persona loading is forbidden")

    _validate_target(snapshot, target, context)

    if not receiver_ack:
        # Clutch overlap: keep old gear engaged; do not expose target layer yet.
        return snapshot.sealed()

    kwargs: dict[str, object] = {
        "current_gear": target,
        "acknowledged_gear": target,
    }
    if target == Gear.G1:
        kwargs["identity_fingerprint"] = str(context["identity_fingerprint"])
        kwargs["governance_fingerprint"] = str(context["governance_fingerprint"])
    elif target == Gear.G2:
        kwargs["base_personality_fingerprint"] = str(context["base_personality_fingerprint"])
    elif target == Gear.G3:
        kwargs["loaded_memory_classes"] = tuple(str(x) for x in context["loaded_memory_classes"])
        kwargs["emotional_context_pointer"] = str(context.get("emotional_context_pointer", ""))
    elif target == Gear.G4:
        kwargs["self_model_pointer"] = str(context.get("self_model_pointer", ""))
    elif target == Gear.G5:
        kwargs["generated_goal_mode"] = "CANDIDATE_ONLY"
    elif target == Gear.G6:
        kwargs["live_overlay_mode"] = str(context.get("live_overlay_mode", "DISABLED"))

    return replace(snapshot, **kwargs).sealed()


def downshift(snapshot: BootSnapshot, target: Gear) -> BootSnapshot:
    """Return to a lower safe gear without inventing new state."""
    _validate_common(snapshot)
    if target < Gear.N or target >= snapshot.current_gear:
        raise BootProtocolError("downshift target must be a lower gear")

    result = snapshot
    if target < Gear.G6:
        result = replace(result, live_overlay_mode="DISABLED")
    if target < Gear.G5:
        result = replace(result, generated_goal_mode="DISABLED")
    if target < Gear.G4:
        result = replace(result, self_model_pointer="")
    if target < Gear.G3:
        result = replace(result, loaded_memory_classes=(), emotional_context_pointer="")
    if target < Gear.G2:
        result = replace(result, base_personality_fingerprint="")
    if target < Gear.G1:
        result = replace(result, identity_fingerprint="", governance_fingerprint="")

    return replace(result, current_gear=target, acknowledged_gear=target).sealed()
