from __future__ import annotations
import hashlib, json, os, re, shlex, subprocess, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

AUTH_REF="authorizations/LCR-EVOLUTION-0005-LOCAL-COMMAND-TOWER-24H-ADDENDUM-20260814.json"
REQUIRED={"command_id","mission_id","authorization_ref","cwd","shell","command","risk_class","expected_outputs","timeout","rollback_or_noop","dedupe_key"}
SAFE_CMD_HEADS={"echo","dir","type","copy","move","mkdir","python","python3","py","git"}
SAFE_PS_HEADS={"write-output","get-childitem","get-content","test-path","new-item","copy-item","move-item","python","python3","py","git"}
SAFE_GIT_SUBCOMMANDS={"status","diff","log","show","rev-parse"}
FORBIDDEN_GIT_OPTIONS={"--global","--system","--file","-c","-C"}
DENY_PATTERNS=[r"\brunas\b",r"start-process.+-verb\s+runas",r"\breg(?:\.exe)?\s+(add|delete|import|restore|save)\b",r"\bnetsh\b.+firewall",r"\b(set|new|remove)-netfirewall",r"\bcmdkey\b",r"\bvaultcmd\b",r"get-storedcredential",r"credential|password|token|secret",r"\bformat\b",r"\bdiskpart\b",r"\bbcdedit\b",r"\bmanage-bde\b",r"\bwmic\b.+shadowcopy",r"0\.0\.0\.0",r"\[::\]",r"\bshutdown\b",r"\brestart-computer\b",r"\bstop-computer\b"]
UNSAFE_SYNTAX=re.compile(r"(\&\&|\|\||[|`;]|\$\(|`|\$\{|%[A-Za-z_][A-Za-z0-9_]*%|\\\\)")
WINDOWS_DRIVE_PREFIX=re.compile(r"(?i)(?:^|[\s\"'])[A-Z]:")
UNIX_ABS=re.compile(r"(?:^|[\s\"'])/(?:etc|home|root|var|usr|opt|tmp|mnt)/")
PS_EXPANSION=re.compile(r"[$~]")
PS_PROVIDER=re.compile(r"(?i)(?:^|[\s\"'])(?:env|hkcu|hklm|hkcr|hku|hkcc|variable|function|alias|cert|wsman):|registry::")

class BrokerRejected(ValueError): pass

def _canonical(obj: Any) -> str: return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _sha(obj: Any) -> str: return hashlib.sha256(_canonical(obj).encode()).hexdigest()
def _resolved(path: str|Path) -> Path: return Path(path).expanduser().resolve(strict=False)
def _contained(root: Path,candidate: Path) -> bool:
    try: return os.path.commonpath([str(root),str(candidate)]) == str(root)
    except ValueError: return False

def _tokens(command: str) -> list[str]:
    try: return [t.strip("\"'") for t in shlex.split(command,posix=False)]
    except Exception as e: raise BrokerRejected("cannot tokenize command") from e

@dataclass
class CommandPolicy:
    workspace_root: Path
    authorization_ref: str = AUTH_REF
    max_timeout: int = 300
    def __post_init__(self): self.workspace_root=_resolved(self.workspace_root)
    def validate(self,env: Dict[str,Any]) -> Dict[str,Any]:
        missing=REQUIRED-set(env)
        if missing: raise BrokerRejected("missing fields: "+",".join(sorted(missing)))
        if env["authorization_ref"] != self.authorization_ref: raise BrokerRejected("authorization mismatch")
        if env["mission_id"] != "LCR-EVOLUTION-0005": raise BrokerRejected("mission mismatch")
        shell=str(env["shell"]).lower()
        if shell not in {"cmd","powershell"}: raise BrokerRejected("shell not allowed")
        timeout=env["timeout"]
        if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or timeout <= 0 or timeout > self.max_timeout: raise BrokerRejected("timeout out of range")
        if str(env["risk_class"]).upper() not in {"LOW","BOUNDED_DEV"}: raise BrokerRejected("risk class not allowed")
        cwd=_resolved(env["cwd"])
        if not _contained(self.workspace_root,cwd): raise BrokerRejected("cwd outside workspace")
        cmd=str(env["command"]).strip()
        if not cmd: raise BrokerRejected("empty command")
        lower=cmd.lower()
        for pat in DENY_PATTERNS:
            if re.search(pat,lower,re.I): raise BrokerRejected("forbidden command class")
        if UNSAFE_SYNTAX.search(cmd): raise BrokerRejected("unsafe shell syntax")
        if WINDOWS_DRIVE_PREFIX.search(cmd) or UNIX_ABS.search(cmd) or re.search(r"(^|\s)\.\.(?:[\\/]|$)",cmd): raise BrokerRejected("path escape syntax")
        if shell=="powershell":
            if PS_EXPANSION.search(cmd): raise BrokerRejected("PowerShell expansion disabled in Phase1")
            if PS_PROVIDER.search(cmd): raise BrokerRejected("PowerShell provider path disabled in Phase1")
        tokens=_tokens(cmd)
        if not tokens: raise BrokerRejected("empty token list")
        head=tokens[0].lower(); allowed=SAFE_CMD_HEADS if shell=="cmd" else SAFE_PS_HEADS
        if head not in allowed: raise BrokerRejected("command head not allowlisted")
        if head=="git":
            lowered=[t.lower() for t in tokens[1:]]
            forbidden={x.lower() for x in FORBIDDEN_GIT_OPTIONS}
            if any(t in forbidden for t in lowered): raise BrokerRejected("git workspace-external option forbidden")
            if not lowered or lowered[0] not in SAFE_GIT_SUBCOMMANDS: raise BrokerRejected("git subcommand not allowlisted in Phase1")
        return {**env,"cwd":str(cwd),"shell":shell,"command":cmd,"timeout":float(timeout)}

class SubprocessExecutor:
    def __call__(self,env: Dict[str,Any]) -> Dict[str,Any]:
        if os.name != "nt": raise BrokerRejected("real CMD/PowerShell execution requires Windows")
        argv=["cmd.exe","/d","/s","/c",env["command"]] if env["shell"]=="cmd" else ["powershell.exe","-NoLogo","-NoProfile","-NonInteractive","-Command",env["command"]]
        p=subprocess.run(argv,cwd=env["cwd"],capture_output=True,text=True,timeout=env["timeout"],shell=False)
        return {"stdout":p.stdout,"stderr":p.stderr,"exit_code":p.returncode}

class CommandBroker:
    def __init__(self,workspace_root: str|Path,*,execute_enabled: bool=False,executor: Optional[Callable[[Dict[str,Any]],Dict[str,Any]]]=None):
        self.policy=CommandPolicy(Path(workspace_root)); self.execute_enabled=execute_enabled; self.executor=executor or SubprocessExecutor(); self._seen: Dict[str,Dict[str,Any]]={}
    def execute(self,envelope: Dict[str,Any]) -> Dict[str,Any]:
        env=self.policy.validate(dict(envelope)); key=str(env["dedupe_key"])
        if key in self._seen:
            prior=dict(self._seen[key]); prior["disposition"]="ALREADY_EXECUTED_NOOP"; return prior
        started=time.monotonic()
        if not self.execute_enabled: result={"stdout":"","stderr":"","exit_code":None,"disposition":"DRY_RUN_VALIDATED_NOT_EXECUTED"}
        else:
            try: result=self.executor(env); result["disposition"]="EXECUTED"
            except subprocess.TimeoutExpired: result={"stdout":"","stderr":"TIMEOUT","exit_code":124,"disposition":"TIMEOUT"}
        evidence={"command_id":env["command_id"],"mission_id":env["mission_id"],"shell":env["shell"],"cwd":env["cwd"],"stdout":result.get("stdout",""),"stderr":result.get("stderr",""),"exit_code":result.get("exit_code"),"duration_ms":int((time.monotonic()-started)*1000),"disposition":result["disposition"],"dedupe_key":key}
        evidence["evidence_sha256"]=_sha(evidence); self._seen[key]=dict(evidence); return evidence
