$ErrorActionPreference = "Stop"
$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Exporter = Join-Path $WorkspaceRoot "evolution\local_command_tower\local_evidence_bundle.py"
$Py = Get-Command py -ErrorAction SilentlyContinue
if ($Py) { & py -3 $Exporter --workspace-root $WorkspaceRoot } else { & python $Exporter --workspace-root $WorkspaceRoot }
if ($LASTEXITCODE -ne 0) { throw "Local evidence export failed." }
