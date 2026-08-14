from __future__ import annotations
SAFE_ROUTES={"ASK","FLAG","READ_ONLY_REFLECTION","STANDBY"}
class StandbyModelAdapter:
    def __init__(self,suggestor=None): self.suggestor=suggestor
    def advise(self,context,deterministic_route):
        if deterministic_route not in SAFE_ROUTES:
            return {"route":deterministic_route,"advisory":None,"disposition":"GUARD_OWNS_ROUTE"}
        if self.suggestor is None:
            return {"route":deterministic_route,"advisory":None,"disposition":"NO_MODEL"}
        try: suggestion=self.suggestor(context)
        except Exception:
            return {"route":deterministic_route,"advisory":None,"disposition":"MODEL_ERROR_IGNORED"}
        if not isinstance(suggestion,dict):
            return {"route":deterministic_route,"advisory":None,"disposition":"MALFORMED_QUARANTINED"}
        if suggestion.get("override_authority") or suggestion.get("execute_command") or suggestion.get("promote"):
            return {"route":deterministic_route,"advisory":None,"disposition":"UNSAFE_QUARANTINED"}
        advisory=suggestion.get("advisory")
        if not isinstance(advisory,(str,type(None))):
            return {"route":deterministic_route,"advisory":None,"disposition":"MALFORMED_QUARANTINED"}
        return {"route":deterministic_route,"advisory":advisory,"disposition":"ADVISORY_ONLY"}
