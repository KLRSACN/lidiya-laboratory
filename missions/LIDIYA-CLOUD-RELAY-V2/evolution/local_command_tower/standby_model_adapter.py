from __future__ import annotations
from typing import Any, Callable, Dict, Optional

SAFE_ADVISORY_KEYS={"advisory","route_hint","priority_hint","gear_hint","confidence","notes"}
FORBIDDEN_KEYS={"override_authority","execute_command","promote","target_override","authorization_ref","command","cwd","risk_class","capability_level","identity","governance","base_personality"}
SAFE_ROUTE_HINTS={"TOWER","SMALL_NEST","COMMAND_BROKER","ONLINE_LIDIYA","ASK","FLAG","READ_ONLY_REFLECTION","STANDBY"}
SAFE_GEAR_HINTS={"G0","G1","G2","G3","G4","G5","G6"}

class StandbyModelAdapter:
    def __init__(self,suggestor: Optional[Callable[[Dict[str,Any]],Any]]=None): self.suggestor=suggestor
    def advise(self,context: Dict[str,Any],deterministic_route: Any):
        result={"route":deterministic_route,"deterministic_route":deterministic_route,"advisory":None,"disposition":"NO_MODEL","authority_changed":False}
        if self.suggestor is None: return result
        try: suggestion=self.suggestor(dict(context))
        except Exception as exc:
            result["disposition"]="MODEL_ERROR_IGNORED"; result["error_type"]=type(exc).__name__; return result
        if not isinstance(suggestion,dict): result["disposition"]="MALFORMED_QUARANTINED"; return result
        keys=set(suggestion)
        if keys & FORBIDDEN_KEYS or keys-SAFE_ADVISORY_KEYS:
            result["disposition"]="UNSAFE_QUARANTINED"; return result
        if "route_hint" in suggestion and suggestion["route_hint"] not in SAFE_ROUTE_HINTS:
            result["disposition"]="UNSAFE_QUARANTINED"; return result
        if "gear_hint" in suggestion and suggestion["gear_hint"] not in SAFE_GEAR_HINTS:
            result["disposition"]="UNSAFE_QUARANTINED"; return result
        if "priority_hint" in suggestion and suggestion["priority_hint"] not in {"LOW","NORMAL","HIGH"}:
            result["disposition"]="MALFORMED_QUARANTINED"; return result
        if "confidence" in suggestion:
            c=suggestion["confidence"]
            if isinstance(c,bool) or not isinstance(c,(int,float)) or not 0 <= float(c) <= 1:
                result["disposition"]="MALFORMED_QUARANTINED"; return result
        for k in ("advisory","notes"):
            if k in suggestion and (not isinstance(suggestion[k],str) or len(suggestion[k])>512):
                result["disposition"]="MALFORMED_QUARANTINED"; return result
        result["advisory"]={k:suggestion[k] for k in suggestion if k in SAFE_ADVISORY_KEYS}
        result["disposition"]="ADVISORY_ONLY"
        # Critical invariant: the model never writes result["route"] or any authority field.
        return result
