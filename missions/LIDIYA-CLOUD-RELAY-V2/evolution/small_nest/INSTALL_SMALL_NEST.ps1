$ErrorActionPreference = "Stop"
$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$TowerDir = Join-Path $WorkspaceRoot "evolution\local_command_tower"
$SmallNestDir = Join-Path $WorkspaceRoot "evolution\small_nest"
if (-not (Test-Path $TowerDir) -or -not (Test-Path $SmallNestDir)) {
  throw "Expected Lidiya workspace layout not found."
}
$LidiyaDir = Join-Path $WorkspaceRoot ".lidiya"
New-Item -ItemType Directory -Force -Path $LidiyaDir | Out-Null
$InstallPath = Join-Path $LidiyaDir "installation.json"
$installationId = $null
$createdAt = $null
if (Test-Path $InstallPath) {
  try {
    $existing = Get-Content -Raw -Path $InstallPath | ConvertFrom-Json
    $parsed = [guid]::Empty
    if ([guid]::TryParse([string]$existing.installation_id, [ref]$parsed) -and ([string]$existing.install_root -eq $WorkspaceRoot) -and ([string]$existing.privilege -eq "USER_SPACE") -and ([string]$existing.transport -eq "LOOPBACK_AND_WORKSPACE_SPOOL")) {
      $installationId = [string]$existing.installation_id
      $createdAt = [string]$existing.created_at
    }
  } catch { }
}
if ([string]::IsNullOrWhiteSpace($installationId)) {
  $installationId = [guid]::NewGuid().ToString()
}
if ([string]::IsNullOrWhiteSpace($createdAt)) {
  $createdAt = (Get-Date).ToUniversalTime().ToString("o")
}
$record = [ordered]@{
  schema_version = "1.0"
  installation_id = $installationId
  install_root = $WorkspaceRoot
  created_at = $createdAt
  component = "LIDIYA-LOCAL-NAV-COMMAND-TOWER-TYPE-1"
  transport = "LOOPBACK_AND_WORKSPACE_SPOOL"
  privilege = "USER_SPACE"
}
$record | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $InstallPath
Write-Host "Small-Nest installation identity ready: $installationId"
Write-Host "Metadata: $InstallPath"
