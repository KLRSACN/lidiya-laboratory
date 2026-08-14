from __future__ import annotations

def route(event):
    kind=str(event.get("kind","")).upper()
    if kind in {"HEALTH","HEARTBEAT"}: return {"gear":"G0","target":"TOWER","wake_model":False}
    if kind=="WAKE": return {"gear":"G1","target":"SMALL_NEST","wake_model":False}
    if kind=="COMMAND": return {"gear":"G2","target":"COMMAND_BROKER","wake_model":False}
    if kind in {"MEMORY_EXPERIMENT","MODEL_ADAPTER","SOFTWARE_PATCH"}: return {"gear":"G3","target":"SMALL_NEST","wake_model":True}
    return {"gear":"G1","target":"ONLINE_LIDIYA","wake_model":False,"reason":"UNKNOWN_OR_HIGHER_CONTEXT"}
