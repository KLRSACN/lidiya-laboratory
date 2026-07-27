[CmdletBinding()]
param(
    [string]$HomeRoot = 'D:\lidiya',
    [string]$InstallRoot = 'D:\lidiya\0.dev_tools\home_bridge_v2'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$App = 'Lidiya Home Bridge'
$Version = '2.0.0-alpha.4'
$Sequence = 5
$StartedAt = Get-Date
$Timestamp = $StartedAt.ToString('yyyyMMdd_HHmmss')

$RuntimeDir = Join-Path $InstallRoot 'runtime'
$LogsDir = Join-Path $InstallRoot 'logs'
$DocsDir = Join-Path $InstallRoot 'docs'
$ReleaseDir = Join-Path $InstallRoot ('releases\' + $Version)
$CurrentPath = Join-Path $InstallRoot 'current.json'
$ProgressPath = Join-Path $RuntimeDir 'ROUND_PROGRESS.json'
$ReportPath = Join-Path $LogsDir ('ROUND5_AUDIT_' + $Timestamp + '.json')
$BaselinePath = Join-Path $RuntimeDir 'FORMAL_BASELINE.json'
$HandoffPath = Join-Path $DocsDir 'HOME_BRIDGE_V2_FORMAL_HANDOFF.md'
$AcceptanceScript = Join-Path $ReleaseDir 'startup_acceptance.ps1'
$AcceptanceCmd = Join-Path $InstallRoot 'RUN_STARTUP_ACCEPTANCE.cmd'
$OnLogonCmd = Join-Path $InstallRoot 'RUN_ONLOGON_UPDATE.cmd'

function Write-JsonFile {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Path
    )
    $Parent = Split-Path -Parent $Path
    if ($Parent -and -not (Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    $Temp = $Path + '.tmp'
    $Object | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Temp -Encoding UTF8
    Move-Item -LiteralPath $Temp -Destination $Path -Force
}

function Get-Sha256Safe {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Find-CloudHome {
    $Candidates = @(
        'G:\我的雲端硬碟\Lidiya Memory',
        'G:\My Drive\Lidiya Memory',
        'H:\我的雲端硬碟\Lidiya Memory',
        'H:\My Drive\Lidiya Memory',
        (Join-Path $env:USERPROFILE 'My Drive\Lidiya Memory')
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate -PathType Container)) {
            return $Candidate
        }
    }
    return $null
}

function Assert-File {
    param([string]$Path,[string]$Code)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw ($Code + ': ' + $Path)
    }
}

try {
    Write-Host '=== Lidiya Home Bridge v2｜Round 5 Formal Baseline ===' -ForegroundColor Cyan

    if (-not (Test-Path -LiteralPath $HomeRoot -PathType Container)) {
        throw "HOME_ROOT_NOT_FOUND: $HomeRoot"
    }
    foreach ($Dir in @($RuntimeDir,$LogsDir,$DocsDir,$ReleaseDir)) {
        if (-not (Test-Path -LiteralPath $Dir)) {
            New-Item -ItemType Directory -Path $Dir -Force | Out-Null
        }
    }

    $CloudRoot = Find-CloudHome
    if (-not $CloudRoot) { throw 'CLOUD_HOME_NOT_FOUND' }
    $CloudRuntime = Join-Path $CloudRoot 'Runtime'
    $CloudHistory = Join-Path $CloudRuntime 'History'
    foreach ($Dir in @($CloudRuntime,$CloudHistory)) {
        if (-not (Test-Path -LiteralPath $Dir)) {
            New-Item -ItemType Directory -Path $Dir -Force | Out-Null
        }
    }

    $Round4StatusPath = Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json'
    $StartupStatusPath = Join-Path $CloudRuntime 'AUTO_UPDATE_STARTUP_STATUS.json'
    $ReleaseManifestPath = Join-Path $CloudRuntime 'HOME_BRIDGE_RELEASE.json'
    Assert-File $Round4StatusPath 'ROUND4_STATUS_NOT_FOUND'
    Assert-File $StartupStatusPath 'STARTUP_STATUS_NOT_FOUND'
    Assert-File $ReleaseManifestPath 'RELEASE_MANIFEST_NOT_FOUND'
    Assert-File $CurrentPath 'CURRENT_STATE_NOT_FOUND'

    $Round4 = Get-Content -LiteralPath $Round4StatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $Startup = Get-Content -LiteralPath $StartupStatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $ReleaseManifest = Get-Content -LiteralPath $ReleaseManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $CurrentBefore = Get-Content -LiteralPath $CurrentPath -Raw -Encoding UTF8 | ConvertFrom-Json

    if ($Round4.result -ne 'ROUND4_PASS_CANDIDATE') {
        throw "ROUND4_NOT_READY: $($Round4.result)"
    }
    if ($Startup.result -ne 'AUTO_UPDATE_STARTUP_INSTALLED') {
        throw "STARTUP_NOT_READY: $($Startup.result)"
    }
    if ([string]$ReleaseManifest.version -ne $Version) {
        throw "RELEASE_VERSION_MISMATCH: $($ReleaseManifest.version)"
    }

    Assert-File ([string]$Startup.startup_file) 'STARTUP_FILE_NOT_FOUND'
    Assert-File ([string]$Startup.updater) 'UPDATER_NOT_FOUND'

    $ManifestChecks = New-Object System.Collections.ArrayList
    $ManifestPass = $true
    foreach ($Entry in $ReleaseManifest.files) {
        $Path = Join-Path $ReleaseDir ([string]$Entry.path)
        $Exists = Test-Path -LiteralPath $Path -PathType Leaf
        $Actual = if ($Exists) { Get-Sha256Safe $Path } else { $null }
        $Expected = ([string]$Entry.sha256).ToLowerInvariant()
        $Match = ($Exists -and $Actual -eq $Expected)
        if (-not $Match) { $ManifestPass = $false }
        [void]$ManifestChecks.Add([PSCustomObject]@{
            path = $Path
            exists = $Exists
            expected_sha256 = $Expected
            actual_sha256 = $Actual
            match = $Match
        })
    }
    if (-not $ManifestPass) { throw 'RELEASE_MANIFEST_VERIFICATION_FAILED' }

    $AcceptanceContent = @'
[CmdletBinding()]
param(
    [ValidateSet('SIMULATION','ONLOGON')]
    [string]$Mode = 'SIMULATION',
    [string]$InstallRoot = 'D:\lidiya\0.dev_tools\home_bridge_v2'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$StartedAt = Get-Date
$RuntimeDir = Join-Path $InstallRoot 'runtime'
$LogsDir = Join-Path $InstallRoot 'logs'
$Updater = Join-Path $InstallRoot 'CHECK_HOME_BRIDGE_UPDATE.cmd'
$Current = Join-Path $InstallRoot 'current.json'

function Write-JsonFile {
    param($Object,[string]$Path)
    $Parent = Split-Path -Parent $Path
    if ($Parent -and -not (Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    $Temp = $Path + '.tmp'
    $Object | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Temp -Encoding UTF8
    Move-Item -LiteralPath $Temp -Destination $Path -Force
}
function Get-Sha256Safe {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Find-CloudHome {
    $Candidates = @(
        'G:\我的雲端硬碟\Lidiya Memory',
        'G:\My Drive\Lidiya Memory',
        'H:\我的雲端硬碟\Lidiya Memory',
        'H:\My Drive\Lidiya Memory',
        (Join-Path $env:USERPROFILE 'My Drive\Lidiya Memory')
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate -PathType Container)) { return $Candidate }
    }
    return $null
}

$Result = 'STARTUP_ACCEPTANCE_FAIL'
$ExitCode = -1
$ErrorMessage = $null
try {
    if (-not (Test-Path -LiteralPath $Updater -PathType Leaf)) { throw "UPDATER_NOT_FOUND: $Updater" }
    if (-not (Test-Path -LiteralPath $RuntimeDir)) { New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null }
    if (-not (Test-Path -LiteralPath $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null }

    $Process = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d','/c',('"' + $Updater + '"')) -Wait -PassThru -WindowStyle Hidden
    $ExitCode = $Process.ExitCode
    if ($ExitCode -ne 0) { throw "UPDATER_EXIT_CODE: $ExitCode" }
    $Result = if ($Mode -eq 'ONLOGON') { 'AUTO_UPDATE_ONLOGON_PASS' } else { 'STARTUP_SIMULATION_PASS' }
} catch {
    $ErrorMessage = $_.Exception.Message
}

$Evidence = [ordered]@{
    schema_version = 2
    result = $Result
    mode = $Mode
    started_at = $StartedAt.ToString('o')
    completed_at = (Get-Date).ToString('o')
    computer_name = $env:COMPUTERNAME
    user_name = $env:USERNAME
    updater = $Updater
    updater_exit_code = $ExitCode
    current_state = $Current
    current_state_sha256 = Get-Sha256Safe $Current
    error = $ErrorMessage
}
$LocalStatus = Join-Path $RuntimeDir 'STARTUP_ACCEPTANCE_STATUS.json'
Write-JsonFile $Evidence $LocalStatus

$CloudRoot = Find-CloudHome
if ($CloudRoot) {
    $CloudRuntime = Join-Path $CloudRoot 'Runtime'
    if (-not (Test-Path -LiteralPath $CloudRuntime)) { New-Item -ItemType Directory -Path $CloudRuntime -Force | Out-Null }
    Write-JsonFile $Evidence (Join-Path $CloudRuntime 'STARTUP_ACCEPTANCE_STATUS.json')
    if ($Mode -eq 'ONLOGON') {
        Write-JsonFile $Evidence (Join-Path $CloudRuntime 'AUTO_UPDATE_LOGIN_EVIDENCE.json')
    }
}
if ($Result -eq 'STARTUP_ACCEPTANCE_FAIL') { exit 1 }
exit 0
'@
    $AcceptanceContent | Set-Content -LiteralPath $AcceptanceScript -Encoding UTF8

    $AcceptanceCmdContent = '@echo off' + [Environment]::NewLine +
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $AcceptanceScript + '" -Mode SIMULATION' + [Environment]::NewLine +
        'exit /b %ERRORLEVEL%' + [Environment]::NewLine
    $AcceptanceCmdContent | Set-Content -LiteralPath $AcceptanceCmd -Encoding ASCII

    $OnLogonCmdContent = '@echo off' + [Environment]::NewLine +
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $AcceptanceScript + '" -Mode ONLOGON' + [Environment]::NewLine +
        'exit /b %ERRORLEVEL%' + [Environment]::NewLine
    $OnLogonCmdContent | Set-Content -LiteralPath $OnLogonCmd -Encoding ASCII

    $StartupFile = [string]$Startup.startup_file
    $Q = [char]34
    $VbsLines = New-Object System.Collections.ArrayList
    [void]$VbsLines.Add('Set shell = CreateObject(' + $Q + 'WScript.Shell' + $Q + ')')
    [void]$VbsLines.Add('WScript.Sleep 60000')
    [void]$VbsLines.Add('shell.Run Chr(34) & ' + $Q + $OnLogonCmd + $Q + ' & Chr(34), 0, False')
    $VbsLines | Set-Content -LiteralPath $StartupFile -Encoding ASCII

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $AcceptanceScript -Mode SIMULATION -InstallRoot $InstallRoot
    $AcceptanceExit = $LASTEXITCODE
    if ($AcceptanceExit -ne 0) { throw "STARTUP_SIMULATION_FAILED: ExitCode=$AcceptanceExit" }

    $SimulationPath = Join-Path $RuntimeDir 'STARTUP_ACCEPTANCE_STATUS.json'
    Assert-File $SimulationPath 'STARTUP_SIMULATION_EVIDENCE_MISSING'
    $Simulation = Get-Content -LiteralPath $SimulationPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Simulation.result -ne 'STARTUP_SIMULATION_PASS') {
        throw "STARTUP_SIMULATION_BAD_RESULT: $($Simulation.result)"
    }

    $RootFiles = @(
        (Join-Path $InstallRoot 'CHECK_HOME_BRIDGE_UPDATE.cmd'),
        (Join-Path $InstallRoot 'ROLLBACK_HOME_BRIDGE.cmd'),
        (Join-Path $InstallRoot 'VALIDATE_ONLINE_HANDOFF.cmd'),
        $AcceptanceCmd,
        $OnLogonCmd,
        $StartupFile,
        (Join-Path $InstallRoot 'config\authority_map.json'),
        (Join-Path $InstallRoot 'schemas\bootstrap_packet.schema.json'),
        (Join-Path $InstallRoot 'schemas\online_handoff.schema.json')
    )
    $RootEvidence = New-Object System.Collections.ArrayList
    foreach ($Path in $RootFiles) {
        $Exists = Test-Path -LiteralPath $Path -PathType Leaf
        [void]$RootEvidence.Add([PSCustomObject]@{
            path = $Path
            exists = $Exists
            sha256 = if ($Exists) { Get-Sha256Safe $Path } else { $null }
            size_bytes = if ($Exists) { (Get-Item -LiteralPath $Path).Length } else { $null }
        })
    }

    $Baseline = [ordered]@{
        schema_version = 2
        app = $App
        baseline_id = ('HOME_BRIDGE_V2_FORMAL_' + $Timestamp)
        version = $Version
        sequence = $Sequence
        status = 'FORMAL_BASELINE'
        approved_scope = @(
            'isolated v2 workspace',
            'Google Drive runtime closed loop',
            'handoff validation and quarantine',
            'SHA256 evidence chain',
            'GitHub update selftest and rollback',
            'user startup auto-update launcher'
        )
        frozen_release = $ReleaseDir
        previous_stable = 'Cloud Bridge v1 (unchanged)'
        created_at = (Get-Date).ToString('o')
        owner = '雷博玄'
        release_manifest = $ReleaseManifestPath
        release_manifest_sha256 = Get-Sha256Safe $ReleaseManifestPath
        release_files = @($ManifestChecks)
        operational_files = @($RootEvidence)
        startup = [ordered]@{
            startup_file = $StartupFile
            delay_seconds = 60
            evidence_file = 'Runtime/AUTO_UPDATE_LOGIN_EVIDENCE.json'
            simulation_result = $Simulation.result
            actual_onlogon_result = 'PENDING_NEXT_LOGIN'
        }
        boundaries = [ordered]@{
            cloud_bridge_v1_modified = $false
            files_deleted = $false
            github_main_modified = $false
            formal_release_hotpatched = $false
        }
    }
    Write-JsonFile $Baseline $BaselinePath

    $HandoffLines = @(
        '# Lidiya Home Bridge v2 正式封版交接',
        '',
        'TYPE：PROJECT / EVIDENCE',
        'LAYER：L2 / L3',
        'STATUS：FORMAL_BASELINE',
        'OWNER：雷博玄',
        ('UPDATED_AT：' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')),
        '',
        '## 正式基準',
        ('- 版本：' + $Version),
        ('- 固定路徑：' + $InstallRoot),
        ('- 凍結 Release：' + $ReleaseDir),
        '- Cloud Bridge v1：保持不變，仍為資料傳輸層。',
        '- Home Bridge v2：治理、交接、驗證、隔離、更新與回滾層。',
        '',
        '## 新視窗最小讀取',
        '1. 00 Lidiya Memory Index',
        '2. Runtime/FORMAL_BASELINE.json',
        '3. Runtime/HOME_BRIDGE_STATUS.json',
        '4. Runtime/ROUND_PROGRESS.json',
        '5. 本文件（只在 Home Bridge 工程任務讀取）',
        '',
        '## 固定入口',
        ('- 更新：' + (Join-Path $InstallRoot 'CHECK_HOME_BRIDGE_UPDATE.cmd')),
        ('- 回滾：' + (Join-Path $InstallRoot 'ROLLBACK_HOME_BRIDGE.cmd')),
        ('- 交接驗證：' + (Join-Path $InstallRoot 'VALIDATE_ONLINE_HANDOFF.cmd')),
        ('- 啟動模擬驗收：' + $AcceptanceCmd),
        '',
        '## 目前狀態',
        '- Round 1～4：證據與雲端讀回完成。',
        '- Round 5：正式基準建立與啟動模擬驗收完成。',
        '- 下一次正常登入後，自動產生 Runtime/AUTO_UPDATE_LOGIN_EVIDENCE.json。',
        '- 在該檔案讀回前，實際 ONLOGON 驗收狀態維持 PENDING，不影響手動更新與回滾。',
        '',
        '## 禁止事項',
        '- 不直接修改凍結 Release。',
        '- 不自動覆蓋 Cloud Bridge v1。',
        '- 不因新模型口頭聲稱而標記成功；以 report、manifest、SHA256 與雲端讀回為準。',
        '- 新功能建立新 Release，不熱修正式基準。'
    )
    $HandoffLines | Set-Content -LiteralPath $HandoffPath -Encoding UTF8

    $Current = [ordered]@{
        schema_version = 2
        app = $App
        active_version = $Version
        active_release = $ReleaseDir
        previous_version = [string]$CurrentBefore.active_version
        previous_release = [string]$CurrentBefore.active_release
        previous_stable = 'Cloud Bridge v1 (unchanged)'
        status = 'FORMAL'
        approval_state = 'FORMAL_BASELINE_APPROVED_STARTUP_SIMULATION_PASS_ONLOGON_PENDING'
        formal_baseline = $BaselinePath
        updated_at = (Get-Date).ToString('o')
    }
    Write-JsonFile $Current $CurrentPath

    $Checks = [ordered]@{
        round4_ready = ($Round4.result -eq 'ROUND4_PASS_CANDIDATE')
        startup_launcher_installed = ($Startup.result -eq 'AUTO_UPDATE_STARTUP_INSTALLED')
        release_manifest_verified = $ManifestPass
        startup_simulation_pass = ($Simulation.result -eq 'STARTUP_SIMULATION_PASS')
        baseline_exists = (Test-Path -LiteralPath $BaselinePath -PathType Leaf)
        handoff_exists = (Test-Path -LiteralPath $HandoffPath -PathType Leaf)
        current_formal = ((Get-Content -LiteralPath $CurrentPath -Raw -Encoding UTF8 | ConvertFrom-Json).status -eq 'FORMAL')
        onlogon_wrapper_exists = (Test-Path -LiteralPath $OnLogonCmd -PathType Leaf)
        startup_vbs_exists = (Test-Path -LiteralPath $StartupFile -PathType Leaf)
    }
    $AllPass = $true
    foreach ($Pair in $Checks.GetEnumerator()) {
        if (-not [bool]$Pair.Value) { $AllPass = $false }
    }
    $Result = if ($AllPass) { 'ROUND5_PASS_CANDIDATE' } else { 'ROUND5_FAIL' }

    $Report = [ordered]@{
        schema_version = 2
        app = $App
        version = $Version
        sequence = $Sequence
        result = $Result
        started_at = $StartedAt.ToString('o')
        completed_at = (Get-Date).ToString('o')
        computer_name = $env:COMPUTERNAME
        checks = $Checks
        paths = [ordered]@{
            install = $InstallRoot
            release = $ReleaseDir
            formal_baseline = $BaselinePath
            formal_handoff = $HandoffPath
            startup_file = $StartupFile
            startup_acceptance_cmd = $AcceptanceCmd
            onlogon_cmd = $OnLogonCmd
            cloud_runtime = $CloudRuntime
        }
        integrity = [ordered]@{
            formal_baseline_sha256 = Get-Sha256Safe $BaselinePath
            formal_handoff_sha256 = Get-Sha256Safe $HandoffPath
            startup_acceptance_sha256 = Get-Sha256Safe $AcceptanceScript
            startup_acceptance_cmd_sha256 = Get-Sha256Safe $AcceptanceCmd
            onlogon_cmd_sha256 = Get-Sha256Safe $OnLogonCmd
            startup_vbs_sha256 = Get-Sha256Safe $StartupFile
            current_state_sha256 = Get-Sha256Safe $CurrentPath
        }
        startup_simulation = $Simulation
        next_step = 'Online cloud readback, then update 00 index with the formal Home Bridge v2 entry. Actual ONLOGON evidence will be read after the next normal login.'
        approval_state = 'CANDIDATE_NOT_FORMALLY_APPROVED'
    }
    Write-JsonFile $Report $ReportPath

    $Progress = [ordered]@{
        schema_version = 2
        project = 'Lidiya Home Bridge v2'
        current_round = 5
        status = $Result
        active_version = $Version
        updated_at = (Get-Date).ToString('o')
        completed = @(
            'round1 inventory and isolation',
            'round2 bootstrap and handoff validator',
            'round3 Drive closed loop and quarantine tests',
            'round4 updater selftest and rollback',
            'startup launcher installation',
            'round5 formal baseline manifest',
            'round5 startup simulation acceptance',
            'formal handoff generated'
        )
        pending = @(
            'online cloud readback of round5 evidence',
            '00 index formal entry',
            'actual ONLOGON evidence after next normal login'
        )
        latest_report = $ReportPath
        cloud_report = (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json')
        next_minimum_step = 'Read FORMAL_BASELINE.json and HOME_BRIDGE_STATUS.json from cloud.'
    }
    Write-JsonFile $Progress $ProgressPath

    foreach ($Name in @('FORMAL_BASELINE.json','HOME_BRIDGE_V2_FORMAL_HANDOFF.md','HOME_BRIDGE_STATUS.json','ROUND_PROGRESS.json','STARTUP_ACCEPTANCE_STATUS.json')) {
        $Existing = Join-Path $CloudRuntime $Name
        if (Test-Path -LiteralPath $Existing -PathType Leaf) {
            $Stem = [System.IO.Path]::GetFileNameWithoutExtension($Name)
            $Ext = [System.IO.Path]::GetExtension($Name)
            Copy-Item -LiteralPath $Existing -Destination (Join-Path $CloudHistory ($Stem + '_' + $Timestamp + $Ext)) -Force
        }
    }

    Copy-Item -LiteralPath $BaselinePath -Destination (Join-Path $CloudRuntime 'FORMAL_BASELINE.json') -Force
    Copy-Item -LiteralPath $HandoffPath -Destination (Join-Path $CloudRuntime 'HOME_BRIDGE_V2_FORMAL_HANDOFF.md') -Force
    Copy-Item -LiteralPath $ReportPath -Destination (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json') -Force
    Copy-Item -LiteralPath $ProgressPath -Destination (Join-Path $CloudRuntime 'ROUND_PROGRESS.json') -Force
    Copy-Item -LiteralPath $SimulationPath -Destination (Join-Path $CloudRuntime 'STARTUP_ACCEPTANCE_STATUS.json') -Force
    Copy-Item -LiteralPath $ReportPath -Destination (Join-Path $CloudRuntime ('ROUND5_AUDIT_' + $Timestamp + '.json')) -Force

    if (-not $AllPass) { throw 'ROUND5_VERIFICATION_FAILED' }

    Write-Host ''
    Write-Host 'ROUND5 PASS CANDIDATE' -ForegroundColor Green
    Write-Host ('Formal baseline: ' + (Join-Path $CloudRuntime 'FORMAL_BASELINE.json'))
    Write-Host ('Formal handoff: ' + (Join-Path $CloudRuntime 'HOME_BRIDGE_V2_FORMAL_HANDOFF.md'))
    Write-Host ('Cloud report: ' + (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json'))
    Write-Host ('Startup simulation: ' + (Join-Path $CloudRuntime 'STARTUP_ACCEPTANCE_STATUS.json'))
    Write-Host 'Actual ONLOGON evidence will be created automatically after the next normal login.'
    exit 0
}
catch {
    $ErrorLine = $_.InvocationInfo.ScriptLineNumber
    $ErrorMessage = $_.Exception.Message
    try {
        if (-not (Test-Path -LiteralPath $LogsDir)) {
            New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
        }
        $Failure = [ordered]@{
            schema_version = 2
            app = $App
            version = $Version
            sequence = $Sequence
            result = 'ROUND5_FAIL'
            updated_at = (Get-Date).ToString('o')
            error_stage = 'ROUND5_FORMAL_BASELINE'
            error_line = $ErrorLine
            error_id = $_.FullyQualifiedErrorId
            error_category = $_.CategoryInfo.Category.ToString()
            error_message = $ErrorMessage
            result_report = $ReportPath
        }
        Write-JsonFile $Failure (Join-Path $LogsDir ('ROUND5_ERROR_' + $Timestamp + '.json'))
        $CloudRootForError = Find-CloudHome
        if ($CloudRootForError) {
            $CloudRuntimeForError = Join-Path $CloudRootForError 'Runtime'
            if (-not (Test-Path -LiteralPath $CloudRuntimeForError)) {
                New-Item -ItemType Directory -Path $CloudRuntimeForError -Force | Out-Null
            }
            Write-JsonFile $Failure (Join-Path $CloudRuntimeForError 'HOME_BRIDGE_STATUS.json')
        }
    } catch {}
    Write-Host ''
    Write-Host ('ROUND5 FAIL: ' + $ErrorMessage) -ForegroundColor Red
    Write-Host ('ERROR_LINE: ' + $ErrorLine) -ForegroundColor Red
    exit 1
}
