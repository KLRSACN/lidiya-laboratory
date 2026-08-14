from __future__ import annotations
import subprocess, sys
from pathlib import Path

def build_runtime_command(workspace_root,state_rel=".lidiya/small_nest_state.json"):
    root=Path(workspace_root).resolve(strict=False); script=root/"evolution"/"small_nest"/"runtime.py"; state=root/state_rel
    return [sys.executable,str(script),"--state",str(state),"wake"]

def launch_runtime(workspace_root):
    root=Path(workspace_root).resolve(strict=False); cmd=build_runtime_command(root)
    return subprocess.Popen(cmd,cwd=str(root),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False)
