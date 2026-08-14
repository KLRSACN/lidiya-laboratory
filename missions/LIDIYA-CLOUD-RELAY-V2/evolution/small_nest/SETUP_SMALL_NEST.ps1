$ErrorActionPreference = "Stop"
$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Install = Join-Path $PSScriptRoot "INSTALL_SMALL_NEST.ps1"
$Bootstrap = Join-Path $PSScriptRoot "bootstrap_windows.ps1"
$Canary = Join-Path $PSScriptRoot "RUN_LOCAL_CANARY.cmd"
$Export = Join-Path $PSScriptRoot "EXPORT_LOCAL_EVIDENCE.ps1"
& powershell.exe -NoLogo -NoProfile -NonInteractive -File $Install
$TowerProcess = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoLogo","-NoProfile","-NonInteractive","-File",$Bootstrap) -WorkingDirectory $WorkspaceRoot -PassThru -WindowStyle Minimized
$healthy = $false
for ($i=0; $i -lt 30; $i++) {
  try {
    $h = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2
    if ($h.ok -eq $true -and $h.binding -eq "LOOPBACK_ONLY") { $healthy = $true; break }
  } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $healthy) { throw "Local Command Tower failed loopback health check." }
& $Canary
if ($LASTEXITCODE -ne 0) { throw "Local canary failed." }
& powershell.exe -NoLogo -NoProfile -NonInteractive -File $Export
Write-Host "Small-Nest setup and local evidence bundle completed."
Write-Host (Join-Path $WorkspaceRoot ".lidiya\outbox\local_evidence_bundle.json")
