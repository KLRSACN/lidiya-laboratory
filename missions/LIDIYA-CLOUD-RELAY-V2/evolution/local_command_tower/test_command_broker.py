import tempfile, unittest
from pathlib import Path
from command_broker import CommandBroker, BrokerRejected, AUTH_REF

class FakeExecutor:
    def __init__(self): self.calls=0
    def __call__(self,env):
        self.calls+=1
        if "SLOW_FIXTURE" in env["command"]:
            import subprocess; raise subprocess.TimeoutExpired(env["command"],env["timeout"])
        return {"stdout":"ok\n","stderr":"","exit_code":0}

class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory(); self.root=Path(self.td.name).resolve(); self.fx=FakeExecutor(); self.b=CommandBroker(self.root,execute_enabled=True,executor=self.fx)
    def tearDown(self): self.td.cleanup()
    def env(self,**kw):
        x={"command_id":"c1","mission_id":"LCR-EVOLUTION-0005","authorization_ref":AUTH_REF,"cwd":str(self.root),"shell":"cmd","command":"echo hello","risk_class":"LOW","expected_outputs":[],"timeout":5,"rollback_or_noop":"NOOP","dedupe_key":"d1"}; x.update(kw); return x
    def reject(self,**kw):
        with self.assertRaises(BrokerRejected): self.b.execute(self.env(**kw))
    def test_valid_harmless_fixture_structured_evidence(self):
        out=self.b.execute(self.env()); self.assertEqual(out["exit_code"],0); self.assertEqual(out["disposition"],"EXECUTED"); self.assertEqual(len(out["evidence_sha256"]),64); self.assertEqual(self.fx.calls,1)
    def test_duplicate_replay_nonexecuting(self):
        self.b.execute(self.env()); b=self.b.execute(self.env()); self.assertEqual(self.fx.calls,1); self.assertEqual(b["disposition"],"ALREADY_EXECUTED_NOOP")
    def test_wrong_authorization(self): self.reject(authorization_ref="wrong")
    def test_outside_cwd(self): self.reject(cwd=str(self.root.parent))
    def test_symlink_cwd_escape_rejected(self):
        outside=self.root.parent/("outside-"+self.root.name); outside.mkdir(exist_ok=True); link=self.root/"escape-link"
        try: link.symlink_to(outside,target_is_directory=True)
        except (OSError,NotImplementedError): self.skipTest("symlink unavailable")
        self.reject(cwd=str(link))
    def test_parent_traversal_command(self): self.reject(command="type ..\\outside.txt")
    def test_absolute_path_command(self): self.reject(command=r"type C:\Windows\win.ini")
    def test_wrong_shell(self): self.reject(shell="bash")
    def test_high_risk(self): self.reject(risk_class="HIGH")
    def test_timeout_out_of_range(self): self.reject(timeout=9999)
    def test_admin_rejected(self): self.reject(command="runas /user:Administrator cmd")
    def test_registry_rejected(self): self.reject(command="reg add HKCU\\Software\\X")
    def test_firewall_rejected(self): self.reject(command="netsh advfirewall set allprofiles state off")
    def test_secret_extraction_rejected(self): self.reject(command="echo token")
    def test_public_bind_syntax_rejected(self): self.reject(command="echo 0.0.0.0")
    def test_shell_chaining_rejected(self): self.reject(command="echo ok && echo second")
    def test_unallowlisted_head_rejected(self): self.reject(command="curl https://example.com")
    def test_powershell_safe_head(self): self.assertEqual(self.b.execute(self.env(shell="powershell",command="Get-ChildItem",dedupe_key="ps"))["exit_code"],0)
    def test_missing_authorization_field(self):
        e=self.env(); del e["authorization_ref"]
        with self.assertRaises(BrokerRejected): self.b.execute(e)
    def test_powershell_home_variable_escape_rejected(self): self.reject(shell="powershell",command="Get-Content $HOME\\.ssh\\id_rsa")
    def test_powershell_tilde_escape_rejected(self): self.reject(shell="powershell",command="Get-Content ~\\.ssh\\id_rsa")
    def test_powershell_env_provider_rejected(self): self.reject(shell="powershell",command="Get-Content Env:OPENAI_API_KEY")
    def test_powershell_registry_provider_rejected(self): self.reject(shell="powershell",command="Get-Content HKCU:\\Software")
    def test_powershell_registry_double_colon_rejected(self): self.reject(shell="powershell",command="Get-Content Registry::HKEY_CURRENT_USER\\Software")
    def test_drive_relative_path_rejected(self): self.reject(shell="powershell",command="Get-Content C:relative.txt")
    def test_git_global_config_rejected(self): self.reject(command="git config --global color.ui auto")
    def test_git_system_config_rejected(self): self.reject(command="git config --system color.ui auto")
    def test_git_status_allowed(self):
        out=self.b.execute(self.env(command="git status",dedupe_key="gitstatus")); self.assertEqual(out["exit_code"],0)
    def test_timeout_returns_evidence(self):
        out=self.b.execute(self.env(command="echo SLOW_FIXTURE",dedupe_key="slow",timeout=1)); self.assertEqual(out["exit_code"],124); self.assertEqual(out["disposition"],"TIMEOUT")

if __name__=="__main__": unittest.main()
