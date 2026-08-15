from __future__ import annotations
from typing import Mapping
ALLOWED_EVENT_TYPES={"EXPERIENCE_APPRAISAL","VALUE_ANCHOR_CANDIDATE","DRIVE_STATE","GOAL_CANDIDATE","OUTCOME_CLOSURE","QUARANTINE","PROTECTED_OBJECT_CANDIDATE"}
def adapt_shadow_event(record:Mapping[str,object])->dict:
    event_type=str(record.get("event_type",""))
    if event_type not in ALLOWED_EVENT_TYPES: raise ValueError("UNSUPPORTED_DASHBOARD_EVENT")
    provenance=record.get("provenance")
    if not isinstance(provenance,dict) or not provenance.get("source_fingerprint"):
        raise ValueError("MISSING_DASHBOARD_PROVENANCE")
    return {"event_type":event_type,"entity_id":str(record.get("entity_id","")),"summary":str(record.get("summary","")),"provenance":dict(provenance),"trust_status":str(record.get("trust_status","UNKNOWN")),"quarantine_reason":record.get("quarantine_reason"),"prediction_outcome":record.get("prediction_outcome"),"authority_from_drive":0,"external_action_set":[],"action_buttons":[],"canonical_personality_mutation":False}
