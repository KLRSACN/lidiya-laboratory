param(
    [string]$ArenaRoot = 'D:\lidiya\0.dev_tools\local_model_arena',
    [string]$Model = 'gemma3n:e2b',
    [int]$MinimumFreeGB = 12
)

$ErrorActionPreference = 'Stop'

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Fail 'Ollama was not found in PATH. Install or repair Ollama before running this candidate installer.'
}

$drive = Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($ArenaRoot).TrimEnd(':','\')) -ErrorAction SilentlyContinue
if (-not $drive) {
    Fail "Cannot resolve the drive for $ArenaRoot"
}

$freeGB = [math]::Floor($drive.Free / 1GB)
if ($freeGB -lt $MinimumFreeGB) {
    Fail "Insufficient free space: ${freeGB}GB available; ${MinimumFreeGB}GB required."
}

$directories = @(
    $ArenaRoot,
    "$ArenaRoot\models",
    "$ArenaRoot\datasets",
    "$ArenaRoot\contracts",
    "$ArenaRoot\evaluations",
    "$ArenaRoot\adapters",
    "$ArenaRoot\runtime",
    "$ArenaRoot\reports",
    "$ArenaRoot\quarantine"
)
foreach ($directory in $directories) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$before = & ollama list 2>&1 | Out-String
$start = Get-Date
& ollama pull $Model
if ($LASTEXITCODE -ne 0) {
    Fail "ollama pull failed for $Model"
}

$show = & ollama show $Model 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Fail "Model was pulled but verification failed for $Model"
}

$report = [ordered]@{
    schema_version = '1.0'
    status = 'LOCAL_MODEL_PULL_VERIFIED'
    model = $Model
    started_at = $start.ToString('o')
    completed_at = (Get-Date).ToString('o')
    arena_root = $ArenaRoot
    free_gb_before = $freeGB
    ollama_path = $ollama.Source
    model_show = $show.Trim()
    preexisting_models = $before.Trim()
}

$reportPath = Join-Path $ArenaRoot 'reports\gemma_pull_latest.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -Path $reportPath -Encoding UTF8
Write-Host "PASS: $Model downloaded and verified. Report: $reportPath"
