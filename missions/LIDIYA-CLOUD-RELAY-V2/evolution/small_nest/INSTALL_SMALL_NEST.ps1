param(
  [string]$WorkspaceRoot = ""
)
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
  $WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
} else {
  $WorkspaceRoot = (Resolve-Path $WorkspaceRoot).Path
}
$LidiyaDir = Join-Path $WorkspaceRoot ".lidiya"
New-Item -ItemType Directory -Force -Path $LidiyaDir | Out-Null
$InstallPath = Join-Path $LidiyaDir "installation.json"
$installationId = $null
if (Test-Path $InstallPath) {
  try {
    $existing = Get-Content -Raw -Path $InstallPath | ConvertFrom-Json
    $parsed = [guid]::Empty
    if ([guid]::TryParse([string]$existing.installation_id, [ref]$parsed) -and ([string]$existing.install_root -eq $WorkspaceRoot)) {
      $installationId = [string]$existing.installation_id
    }
  } catch { }
}
if ([string]::IsNullOrWhiteSpace($installationId)) {
  $installationId = [guid]::NewGuid().ToString()
}
$record = [ordered]@{
  schema_version = "1.0"
  installation_id = $installationId
  install_root = $WorkspaceRoot
  created_at = (Get-Date).ToUniversalTime().ToString("o")
  component = "LIDIYA-LOCAL-NAV-COMMAND-TOWER-TYPE-1"
  transport = "LOOPBACK_AND_WORKSPACE_SPOOL"
  privilege = "USER_SPACE"
}
$record | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $InstallPath
Write-Host "Small-Nest installation identity ready: $installationId"
Write-Host "Metadata: $InstallPath"
