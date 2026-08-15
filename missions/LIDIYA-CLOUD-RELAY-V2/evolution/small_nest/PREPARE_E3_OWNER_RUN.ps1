$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LidiyaDir = Join-Path $Root ".lidiya"
$Install = Join-Path $Root "evolution\small_nest\INSTALL_SMALL_NEST.ps1"
$Start = Join-Path $Root "evolution\small_nest\START_SMALL_NEST.cmd"
$Health = Join-Path $Root "evolution\small_nest\CHECK_SMALL_NEST_HEALTH.ps1"
$Canary = Join-Path $Root "evolution\small_nest\RUN_LOCAL_CANARY.cmd"
$LocalCanaryPy = Join-Path $Root "evolution\local_command_tower\local_canary.py"
$ReconcilerPy = Join-Path $Root "evolution\local_command_tower\evidence_reconciler.py"
$PrepareSelf = Join-Path $Root "evolution\small_nest\PREPARE_E3_OWNER_RUN.ps1"
$OwnerRunContract = Join-Path $Root "evolution\small_nest\E3_OWNER_RUN_CONTRACT.json"
$BundleValidatorPy = Join-Path $Root "evolution\local_command_tower\e3_evidence_bundle.py"
$Required = @($Install,$Start,$Health,$Canary,$LocalCanaryPy,$ReconcilerPy,$PrepareSelf,$OwnerRunContract,$BundleValidatorPy)

foreach ($p in $Required) {
  if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
    throw "Missing required E3 package file: $p"
  }
}
New-Item -ItemType Directory -Force -Path $LidiyaDir | Out-Null

& powershell.exe -NoLogo -NoProfile -NonInteractive -File $Install
if ($LASTEXITCODE -ne 0) { throw "INSTALL_SMALL_NEST failed" }

$healthObserved = $false
try {
  & powershell.exe -NoLogo -NoProfile -NonInteractive -File $Health | Out-Null
  if ($LASTEXITCODE -eq 0) { $healthObserved = $true }
} catch { }
if (-not $healthObserved) {
  Start-Process -FilePath "cmd.exe" -ArgumentList @("/d","/c",('"' + $Start + '"')) -WorkingDirectory $Root | Out-Null
  for ($i = 0; $i -lt 10 -and -not $healthObserved; $i++) {
    Start-Sleep -Milliseconds 500
    try {
      & powershell.exe -NoLogo -NoProfile -NonInteractive -File $Health | Out-Null
      if ($LASTEXITCODE -eq 0) { $healthObserved = $true }
    } catch { }
  }
}
if (-not $healthObserved) { throw "Loopback health was not observed at 127.0.0.1:8765" }

& cmd.exe /d /c ('"' + $Canary + '"')
if ($LASTEXITCODE -ne 0) { throw "RUN_LOCAL_CANARY failed" }

$InstallPath = Join-Path $LidiyaDir "installation.json"
$CanaryPath = Join-Path $LidiyaDir "local_canary_evidence.json"
if (-not (Test-Path -LiteralPath $InstallPath -PathType Leaf)) { throw "Missing installation evidence" }
if (-not (Test-Path -LiteralPath $CanaryPath -PathType Leaf)) { throw "Missing local canary evidence" }

$installation = Get-Content -Raw -LiteralPath $InstallPath | ConvertFrom-Json
$canaryEvidence = Get-Content -Raw -LiteralPath $CanaryPath | ConvertFrom-Json

$resolvedInstallRoot = (Resolve-Path -LiteralPath ([string]$installation.install_root)).Path
if ($resolvedInstallRoot -ne $Root) { throw "Installation root is not the fixed workspace root" }
$parsedInstallationId = [guid]::Empty
if (-not [guid]::TryParse([string]$installation.installation_id, [ref]$parsedInstallationId)) { throw "Installation ID is not a UUID" }
if ([string]$installation.privilege -ne "USER_SPACE") { throw "Installation privilege is not USER_SPACE" }
if ([string]$installation.transport -ne "LOOPBACK_AND_WORKSPACE_SPOOL") { throw "Installation transport mismatch" }
if ([string]$canaryEvidence.mode -ne "WINDOWS_FIXED_HARMLESS_ECHO") { throw "Unexpected canary mode" }
if ([string]$canaryEvidence.command_id -ne "LOCAL-CANARY-ECHO-001") { throw "Unexpected canary command" }
if ([bool]$canaryEvidence.arbitrary_command_input) { throw "Arbitrary command input is forbidden" }
if ([string]$canaryEvidence.stdout -notmatch '^\s*LIDIYA_CANARY\s*$') { throw "Unexpected canary stdout" }
if ([int]$canaryEvidence.exit_code -ne 0) { throw "Canary exit code was nonzero" }
if ([string]$canaryEvidence.installation_id -ne [string]$installation.installation_id) { throw "Canary installation ID mismatch" }
if ((Resolve-Path -LiteralPath ([string]$canaryEvidence.install_root)).Path -ne $Root) { throw "Canary install root mismatch" }

$packageFiles = [ordered]@{}
$relativeMap = [ordered]@{
  "evolution/small_nest/INSTALL_SMALL_NEST.ps1" = $Install
  "evolution/small_nest/START_SMALL_NEST.cmd" = $Start
  "evolution/small_nest/CHECK_SMALL_NEST_HEALTH.ps1" = $Health
  "evolution/small_nest/RUN_LOCAL_CANARY.cmd" = $Canary
  "evolution/local_command_tower/local_canary.py" = $LocalCanaryPy
  "evolution/local_command_tower/evidence_reconciler.py" = $ReconcilerPy
  "evolution/small_nest/PREPARE_E3_OWNER_RUN.ps1" = $PrepareSelf
  "evolution/small_nest/E3_OWNER_RUN_CONTRACT.json" = $OwnerRunContract
  "evolution/local_command_tower/e3_evidence_bundle.py" = $BundleValidatorPy
}
foreach ($entry in $relativeMap.GetEnumerator()) {
  $packageFiles[$entry.Key] = (Get-FileHash -Algorithm SHA256 -LiteralPath $entry.Value).Hash.ToLowerInvariant()
}

$bundle = [ordered]@{
  schema_version = "1.0"
  mission_id = "LCR-EVOLUTION-0005"
  authorization_ref = "authorizations/LCR-EVOLUTION-0005-LOCAL-COMMAND-TOWER-24H-ADDENDUM-20260814.json"
  capture_mode = "OWNER_WINDOWS_LOCAL_PACKAGE"
  installation = $installation
  canary = $canaryEvidence
  health = [ordered]@{
    host = "127.0.0.1"
    port = 8765
    observed = $true
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  package_files = $packageFiles
  promotion_status = "E3_EVIDENCE_READY_FOR_ONLINE_ATTESTATION"
  E3_promoted = $false
}
$BundlePath = Join-Path $LidiyaDir "e3_owner_run_bundle.json"
$bundle | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 -LiteralPath $BundlePath

$validated = $false
& py -3 $BundleValidatorPy --bundle $BundlePath --workspace-root $Root | Out-Null
if ($LASTEXITCODE -eq 0) { $validated = $true }
if (-not $validated) {
  & python $BundleValidatorPy --bundle $BundlePath --workspace-root $Root | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "E3 evidence bundle validation failed" }
}

Write-Host "E3 owner-run evidence ready for online attestation: $BundlePath"
Write-Host "E3_promoted=false. No promotion has been performed."
