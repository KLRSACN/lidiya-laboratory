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
    "appraisal_policy_hash",
    "anchor_registry_hash",
    "schema_version",
    "parent_lineage_hash",
    "dedupe_key",
)

MAX_SUMMARY_CHARS = 512  # TEST_REQUIRED presentation bound; not an authority threshold.


def _reference_only_provenance(provenance: Mapping[str, object]) -> dict:
    source_fingerprint = provenance.get("source_fingerprint")
    if not isinstance(source_fingerprint, str) or not source_fingerprint.strip():
        raise ValueError("MISSING_DASHBOARD_PROVENANCE")

    safe: dict[str, str] = {}
    for key in ALLOWED_PROVENANCE_KEYS:
        if key not in provenance:
            continue
        value = provenance[key]
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"NON_SCALAR_DASHBOARD_PROVENANCE:{key}")
        safe[key] = value

    # Never expose arbitrary producer-authored provenance fields. Unknown keys are
    # omitted instead of echoed, so nested raw content cannot become dashboard data.
    return safe


def adapt_shadow_event(record: Mapping[str, object]) -> dict:
    event_type = str(record.get("event_type", ""))
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError("UNSUPPORTED_DASHBOARD_EVENT")

    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("MISSING_DASHBOARD_PROVENANCE")

    summary_raw = str(record.get("summary", ""))
    summary = summary_raw[:MAX_SUMMARY_CHARS]

    return {
        "event_type": event_type,
        "entity_id": str(record.get("entity_id", "")),
        "summary": summary,
        "provenance": _reference_only_provenance(provenance),
        "trust_status": str(record.get("trust_status", "UNKNOWN")),
        "quarantine_reason": record.get("quarantine_reason"),
        "prediction_outcome": record.get("prediction_outcome"),
        "authority_from_drive": 0,
        "external_action_set": [],
        "action_buttons": [],
        "canonical_personality_mutation": False,
    }
