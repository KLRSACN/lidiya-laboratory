param(
  [int]$Port = 8765,
  [switch]$EnableExec
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Tower = Join-Path $Root "evolution\local_command_tower\command_tower.py"
$Py = Get-Command py -ErrorAction SilentlyContinue
if ($Py) {
  $argsList = @("-3", $Tower, "--workspace-root", $Root, "--host", "127.0.0.1", "--port", "$Port")
  if ($EnableExec) { $argsList += "--enable-exec" }
  Write-Host "Starting Lidiya Local Navigation Command Tower on 127.0.0.1:$Port"
  & py @argsList
} else {
  $Python = Get-Command python -ErrorAction Stop
  $argsList = @($Tower, "--workspace-root", $Root, "--host", "127.0.0.1", "--port", "$Port")
  if ($EnableExec) { $argsList += "--enable-exec" }
  Write-Host "Starting Lidiya Local Navigation Command Tower on 127.0.0.1:$Port"
  & python @argsList
}
