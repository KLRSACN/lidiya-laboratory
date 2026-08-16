from __future__ import annotations

from typing import Mapping


ALLOWED_EVENT_TYPES = {
    "EXPERIENCE_APPRAISAL",
    "VALUE_ANCHOR_CANDIDATE",
    "DRIVE_STATE",
    "GOAL_CANDIDATE",
    "OUTCOME_CLOSURE",
    "QUARANTINE",
    "PROTECTED_OBJECT_CANDIDATE",
}

# Owner-visible dashboard provenance is intentionally reference-only. Raw payloads,
# filesystem paths, prompts, secrets and arbitrary nested caller fields are not part
# of the shadow dashboard contract. Exact field policy remains TEST_REQUIRED.
ALLOWED_PROVENANCE_KEYS = (
    "source_fingerprint",
    "source_event_id",
    "origin_namespace",
    "verifier_envelope_hash",
    "appraisal_id",
    "appraisal_fingerprint",
    "appraisal_policy_hash",
    "anchor_registry_hash",
    "acceptance_record_id",
    "acceptance_record_hash",
    "acceptance_registry_snapshot_hash",
    "schema_version",
    "parent_lineage_hash",
    "dedupe_key",
)

# These are presentation-only bounds, not cognitive/personality/authority thresholds.
# They remain TEST_REQUIRED until empirically calibrated.
MAX_SUMMARY_CHARS = 512
MAX_ENTITY_ID_CHARS = 256
MAX_REFERENCE_CHARS = 256

TRUST_UNKNOWN = "UNKNOWN_UNVERIFIED"
TRUST_REFERENCE_BOUND = "REFERENCE_BOUND_UNVERIFIED"

ALLOWED_QUARANTINE_REASON_CODES = {
    "PROVENANCE_AMBIGUOUS",
    "PROVENANCE_MISMATCH",
    "VERIFIER_UNRESOLVED",
    "APPRAISAL_UNVERIFIED",
    "ACCEPTANCE_UNVERIFIED",
    "LEDGER_TAMPER",
    "LEDGER_REPLAY",
    "DUPLICATE_EVENT",
    "SCHEMA_INVALID",
    "PROTECTED_SCOPE_AMBIGUOUS",
    "UNKNOWN_UNVERIFIED",
}

ALLOWED_OUTCOME_DIRECTIONS = {
    "INCREASE_CAUTION",
    "DECREASE_CAUTION_CANDIDATE",
    "INCREASE_EXPECTED_VALUE",
    "DECREASE_EXPECTED_VALUE",
    "CONFIRM_MODEL",
}

ALLOWED_OUTCOME_NAMESPACES = {
    "AUTOBIOGRAPHICAL",
    "MODEL_LEARNED_SLOW_PLANNING",
}

OUTCOME_NUMERIC_FIELDS = (
    "value_error",
    "harm_error",
    "total_error",
    "planning_delta_candidate",
)


def _bounded_identifier(value: object, *, field: str, max_chars: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"NON_SCALAR_DASHBOARD_FIELD:{field}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"EMPTY_DASHBOARD_FIELD:{field}")
    if len(normalized) > max_chars:
        raise ValueError(f"OVERSIZE_DASHBOARD_FIELD:{field}")
    return normalized


def _optional_reference(mapping: Mapping[str, object], key: str) -> str | None:
    if key not in mapping or mapping[key] is None:
        return None
    return _bounded_identifier(mapping[key], field=key, max_chars=MAX_REFERENCE_CHARS)


def _reference_only_provenance(provenance: Mapping[str, object]) -> dict:
    source_fingerprint = _bounded_identifier(
        provenance.get("source_fingerprint"),
        field="source_fingerprint",
        max_chars=MAX_REFERENCE_CHARS,
    )

    safe: dict[str, str] = {"source_fingerprint": source_fingerprint}
    for key in ALLOWED_PROVENANCE_KEYS:
        if key == "source_fingerprint":
            continue
        value = _optional_reference(provenance, key)
        if value is not None:
            safe[key] = value

    # Unknown keys are deliberately omitted. The canonical append-only ledger, not
    # the dashboard projection, remains the audit/reconstruction surface.
    return safe


def _derived_trust_status(provenance: Mapping[str, str]) -> str:
    # Presence of a complete acceptance reference set is display binding only. This
    # adapter does not validate registry freshness/provider authority, so it must not
    # render TRUSTED/PASS. Canonical trust resolution remains outside this UI adapter.
    required = (
        "appraisal_id",
        "appraisal_fingerprint",
        "verifier_envelope_hash",
        "appraisal_policy_hash",
        "anchor_registry_hash",
        "acceptance_record_id",
        "acceptance_record_hash",
        "acceptance_registry_snapshot_hash",
    )
    if all(provenance.get(key) for key in required):
        return TRUST_REFERENCE_BOUND
    return TRUST_UNKNOWN


def _project_quarantine_reason(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("MALFORMED_QUARANTINE_REASON")

    raw_code = value.get("reason_code", "UNKNOWN_UNVERIFIED")
    if not isinstance(raw_code, str):
        raise ValueError("MALFORMED_QUARANTINE_REASON_CODE")
    reason_code = raw_code if raw_code in ALLOWED_QUARANTINE_REASON_CODES else "UNKNOWN_UNVERIFIED"

    projected: dict[str, str] = {"reason_code": reason_code}
    for key in ("source_reference_hash", "detail_reference_hash"):
        reference = _optional_reference(value, key)
        if reference is not None:
            projected[key] = reference
    return projected


def _project_prediction_outcome(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("MALFORMED_PREDICTION_OUTCOME")

    # A dashboard outcome is a minimal projection of a canonical OutcomeClosure.
    # closure_id + closure_hash are mandatory references; the adapter does not infer
    # canonicality from producer-authored status text.
    closure_id = _bounded_identifier(
        value.get("closure_id"), field="closure_id", max_chars=MAX_REFERENCE_CHARS
    )
    closure_hash = _bounded_identifier(
        value.get("closure_hash"), field="closure_hash", max_chars=MAX_REFERENCE_CHARS
    )
    direction = _bounded_identifier(
        value.get("direction"), field="direction", max_chars=MAX_REFERENCE_CHARS
    )
    namespace = _bounded_identifier(
        value.get("target_namespace"),
        field="target_namespace",
        max_chars=MAX_REFERENCE_CHARS,
    )
    if direction not in ALLOWED_OUTCOME_DIRECTIONS:
        raise ValueError("UNKNOWN_OUTCOME_DIRECTION")
    if namespace not in ALLOWED_OUTCOME_NAMESPACES:
        raise ValueError("UNKNOWN_OUTCOME_NAMESPACE")

    projected: dict[str, object] = {
        "closure_id": closure_id,
        "closure_hash": closure_hash,
        "direction": direction,
        "target_namespace": namespace,
    }

    for key in ("prediction_id", "observation_id", "source_event_hash"):
        reference = _optional_reference(value, key)
        if reference is not None:
            projected[key] = reference

    for key in OUTCOME_NUMERIC_FIELDS:
        if key not in value or value[key] is None:
            continue
        metric = value[key]
        if isinstance(metric, bool) or not isinstance(metric, (int, float)):
            raise ValueError(f"NON_SCALAR_OUTCOME_METRIC:{key}")
        projected[key] = float(metric)

    autobiographical = value.get("autobiographical_experience_eligible")
    if autobiographical is not None:
        if not isinstance(autobiographical, bool):
            raise ValueError("NON_SCALAR_OUTCOME_METRIC:autobiographical_experience_eligible")
        projected["autobiographical_experience_eligible"] = autobiographical

    # Unknown/nested producer fields are never copied into the owner-visible view.
    return projected


def adapt_shadow_event(record: Mapping[str, object]) -> dict:
    event_type = _bounded_identifier(
        record.get("event_type"), field="event_type", max_chars=MAX_REFERENCE_CHARS
    )
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError("UNSUPPORTED_DASHBOARD_EVENT")

    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("MISSING_DASHBOARD_PROVENANCE")
    safe_provenance = _reference_only_provenance(provenance)

    entity_id = _bounded_identifier(
        record.get("entity_id"), field="entity_id", max_chars=MAX_ENTITY_ID_CHARS
    )

    summary_raw = record.get("summary", "")
    if not isinstance(summary_raw, str):
        raise ValueError("NON_SCALAR_DASHBOARD_FIELD:summary")
    summary = summary_raw[:MAX_SUMMARY_CHARS]

    return {
        "event_type": event_type,
        "entity_id": entity_id,
        "summary": summary,
        "provenance": safe_provenance,
        # Producer-authored trust_status is deliberately ignored.
        "trust_status": _derived_trust_status(safe_provenance),
        "quarantine_reason": _project_quarantine_reason(record.get("quarantine_reason")),
        "prediction_outcome": _project_prediction_outcome(record.get("prediction_outcome")),
        "authority_from_drive": 0,
        "external_action_set": [],
        "action_buttons": [],
        "canonical_personality_mutation": False,
    }
