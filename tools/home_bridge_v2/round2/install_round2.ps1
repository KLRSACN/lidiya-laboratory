[CmdletBinding()]
param(
    [string]$HomeRoot = 'D:\lidiya',
    [string]$InstallRoot = 'D:\lidiya\0.dev_tools\home_bridge_v2'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$App = 'Lidiya Home Bridge'
$Version = '2.0.0-alpha.2'
$StartedAt = Get-Date
$Timestamp = $StartedAt.ToString('yyyyMMdd_HHmmss')

$RuntimeDir = Join-Path $InstallRoot 'runtime'
$LogsDir = Join-Path $InstallRoot 'logs'
$ConfigDir = Join-Path $InstallRoot 'config'
$SchemasDir = Join-Path $InstallRoot 'schemas'
$InboxDir = Join-Path $InstallRoot 'inbox'
$OutboxDir = Join-Path $InstallRoot 'outbox'
$QuarantineDir = Join-Path $InstallRoot 'quarantine'
$ReleaseDir = Join-Path $InstallRoot ('releases\' + $Version)
$ReportPath = Join-Path $LogsDir ('ROUND2_AUDIT_' + $Timestamp + '.json')
$ProgressPath = Join-Path $RuntimeDir 'ROUND_PROGRESS.json'
$BootstrapPath = Join-Path $RuntimeDir 'BOOTSTRAP_PACKET.json'
$HandoffTemplatePath = Join-Path $OutboxDir 'ONLINE_HANDOFF.template.json'
$ValidatorPath = Join-Path $ReleaseDir 'validate_online_handoff.ps1'
$ValidatorCmdPath = Join-Path $InstallRoot 'VALIDATE_ONLINE_HANDOFF.cmd'

function Write-JsonFile {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Path
    )
    $Parent = Split-Path -Parent $Path
    if ($Parent -and -not (Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    $Object | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $Path -Encoding UTF8
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

try {
    Write-Host '=== Lidiya Home Bridge v2｜Round 2 ===' -ForegroundColor Cyan

    if (-not (Test-Path -LiteralPath $HomeRoot -PathType Container)) {
        throw "HOME_ROOT_NOT_FOUND: $HomeRoot"
    }

    $RequiredDirs = @(
        $InstallRoot, $RuntimeDir, $LogsDir, $ConfigDir, $SchemasDir,
        $InboxDir, $OutboxDir, $QuarantineDir, $ReleaseDir
    )
    foreach ($Dir in $RequiredDirs) {
        if (-not (Test-Path -LiteralPath $Dir)) {
            New-Item -ItemType Directory -Path $Dir -Force | Out-Null
        }
    }

    $Round1Progress = Join-Path $RuntimeDir 'ROUND_PROGRESS.json'
    if (-not (Test-Path -LiteralPath $Round1Progress -PathType Leaf)) {
        throw "ROUND1_PROGRESS_NOT_FOUND: $Round1Progress"
    }
    $Round1State = Get-Content -LiteralPath $Round1Progress -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Round1State.status -ne 'ROUND1_PASS_CANDIDATE') {
        throw "ROUND1_NOT_READY: $($Round1State.status)"
    }

    $AuthorityMapPath = Join-Path $ConfigDir 'authority_map.json'
    $BootstrapSchemaPath = Join-Path $SchemasDir 'bootstrap_packet.schema.json'
    $HandoffSchemaPath = Join-Path $SchemasDir 'online_handoff.schema.json'
    foreach ($RequiredFile in @($AuthorityMapPath,$BootstrapSchemaPath,$HandoffSchemaPath)) {
        if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
            throw "ROUND1_REQUIRED_FILE_MISSING: $RequiredFile"
        }
    }

    $CloudRoot = Find-CloudHome
    if (-not $CloudRoot) {
        throw 'CLOUD_HOME_NOT_FOUND'
    }
    $CloudRuntime = Join-Path $CloudRoot 'Runtime'
    $CloudHistory = Join-Path $CloudRuntime 'History'
    if (-not (Test-Path -LiteralPath $CloudRuntime)) {
        New-Item -ItemType Directory -Path $CloudRuntime -Force | Out-Null
    }
    if (-not (Test-Path -LiteralPath $CloudHistory)) {
        New-Item -ItemType Directory -Path $CloudHistory -Force | Out-Null
    }

    foreach ($Name in @('HOME_BRIDGE_STATUS.json','ROUND_PROGRESS.json','BOOTSTRAP_PACKET.json','HANDOFF_VALIDATION_STATUS.json')) {
        $Existing = Join-Path $CloudRuntime $Name
        if (Test-Path -LiteralPath $Existing -PathType Leaf) {
            $ArchivedName = ([System.IO.Path]::GetFileNameWithoutExtension($Name) + '_' + $Timestamp + [System.IO.Path]::GetExtension($Name))
            Copy-Item -LiteralPath $Existing -Destination (Join-Path $CloudHistory $ArchivedName) -Force
        }
    }

    $Bootstrap = [ordered]@{
        schema_version = 2
        packet_id = ('BOOTSTRAP_' + $Timestamp)
        generated_at = (Get-Date).ToString('o')
        authority = [ordered]@{
            owner = '雷博玄'
            local_home_root = $HomeRoot
            cloud_home_root = $CloudRoot
            local_bridge_v2 = $InstallRoot
            active_version = $Version
            approval_state = 'ROUND2_CANDIDATE_NOT_FORMALLY_APPROVED'
        }
        routing = [ordered]@{
            minimal_boot_chain = @(
                '00 Lidiya Memory Index',
                '31 Lidiya 新視窗核心摘要與任務分流 20260723',
                '32 Lidiya OS v2 分層架構、權威順位與模組路由 20260723',
                '33 Lidiya HOME 家的正式定義與核心邊界 20260723'
            )
            task_type = 'ENGINEERING_WINDOWS_HOME_BRIDGE'
            task_read_order = @(
                '00 Lidiya Memory Index',
                '25 Lidiya 家同步最高順位、成功指令模式與線上核心協作協定 20260719',
                '26 Lidiya 路徑先詢問、證據永久化、結案清理與線上本地共成長協定 20260719',
                '27 Lidiya 原檔唯讀、複製開發、Claude 協作與版本開發鏈協定 20260719',
                'Runtime/HOME_BRIDGE_STATUS.json',
                'Runtime/ROUND_PROGRESS.json'
            )
            current_project = 'Lidiya Home Bridge v2'
            current_round = 2
            latest_status_file = 'Runtime/HOME_BRIDGE_STATUS.json'
            online_handoff_file = 'Runtime/ONLINE_HANDOFF.json'
            next_action = 'Read this packet, then use the task route and latest status only.'
        }
        state = [ordered]@{
            round1_result = $Round1State.status
            round1_version = $Round1State.active_version
            completed = @(
                'v1 read-only audit',
                'v1 snapshot',
                'v2 isolated workspace',
                'authority map',
                'bootstrap and handoff schemas'
            )
            pending = @(
                'online handoff submission',
                'valid handoff acceptance test',
                'invalid handoff quarantine test',
                'full closed-loop test',
                'GitHub release updater'
            )
        }
        integrity = [ordered]@{
            authority_map_sha256 = Get-Sha256Safe $AuthorityMapPath
            bootstrap_schema_sha256 = Get-Sha256Safe $BootstrapSchemaPath
            handoff_schema_sha256 = Get-Sha256Safe $HandoffSchemaPath
            round1_progress_sha256 = Get-Sha256Safe $Round1Progress
        }
    }
    Write-JsonFile $Bootstrap $BootstrapPath

    $HandoffTemplate = [ordered]@{
        schema_version = 2
        session_id = ('REPLACE_WITH_SESSION_' + $Timestamp)
        updated_at = (Get-Date).ToString('o')
        task = 'Lidiya Home Bridge v2'
        completed = @()
        decisions = @()
        files_created = @()
        files_modified = @()
        lessons_learned = @()
        next_actions = @()
        requires_approval = $true
    }
    Write-JsonFile $HandoffTemplate $HandoffTemplatePath

    $ValidatorContent = @'
[CmdletBinding()]
param(
    [string]$InstallRoot = 'D:\lidiya\0.dev_tools\home_bridge_v2',
    [string]$CloudRoot = '',
    [switch]$AllowMissing
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$Timestamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$RuntimeDir = Join-Path $InstallRoot 'runtime'
$InboxDir = Join-Path $InstallRoot 'inbox'
$QuarantineDir = Join-Path $InstallRoot 'quarantine'
$LogsDir = Join-Path $InstallRoot 'logs'

function Write-JsonFile {
    param($Object,[string]$Path)
    $Parent = Split-Path -Parent $Path
    if ($Parent -and -not (Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    $Object | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $Path -Encoding UTF8
}
function Get-Sha256Safe {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Has-Property {
    param($Object,[string]$Name)
    return [bool]($Object.PSObject.Properties.Name -contains $Name)
}
function Is-ArrayValue {
    param($Value)
    return ($null -ne $Value -and $Value -is [System.Array])
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

if (-not $CloudRoot) { $CloudRoot = Find-CloudHome }
if (-not $CloudRoot) { throw 'CLOUD_HOME_NOT_FOUND' }

foreach ($Dir in @($RuntimeDir,$InboxDir,$QuarantineDir,$LogsDir)) {
    if (-not (Test-Path -LiteralPath $Dir)) { New-Item -ItemType Directory -Path $Dir -Force | Out-Null }
}

$CloudRuntime = Join-Path $CloudRoot 'Runtime'
if (-not (Test-Path -LiteralPath $CloudRuntime)) { New-Item -ItemType Directory -Path $CloudRuntime -Force | Out-Null }
$Source = Join-Path $CloudRuntime 'ONLINE_HANDOFF.json'
$LocalStatus = Join-Path $RuntimeDir 'HANDOFF_VALIDATION_STATUS.json'
$CloudStatus = Join-Path $CloudRuntime 'HANDOFF_VALIDATION_STATUS.json'

if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
    $Missing = [ordered]@{
        schema_version = 2
        result = 'WAITING_FOR_ONLINE_HANDOFF'
        updated_at = (Get-Date).ToString('o')
        source = $Source
        accepted_file = $null
        quarantine_file = $null
        errors = @()
    }
    Write-JsonFile $Missing $LocalStatus
    Write-JsonFile $Missing $CloudStatus
    if ($AllowMissing) { exit 0 }
    exit 2
}

$Errors = New-Object System.Collections.ArrayList
try {
    $Data = Get-Content -LiteralPath $Source -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    [void]$Errors.Add('JSON_PARSE_FAILED: ' + $_.Exception.Message)
    $Data = $null
}

if ($null -ne $Data) {
    $Required = @('schema_version','session_id','updated_at','task','completed','decisions','next_actions','requires_approval')
    foreach ($Name in $Required) {
        if (-not (Has-Property $Data $Name)) { [void]$Errors.Add('MISSING_PROPERTY: ' + $Name) }
    }

    if (Has-Property $Data 'schema_version') {
        if ([int]$Data.schema_version -ne 2) { [void]$Errors.Add('INVALID_SCHEMA_VERSION') }
    }
    foreach ($Name in @('session_id','updated_at','task')) {
        if (Has-Property $Data $Name) {
            $Value = [string]($Data.$Name)
            if ([string]::IsNullOrWhiteSpace($Value)) { [void]$Errors.Add('EMPTY_STRING: ' + $Name) }
        }
    }
    foreach ($Name in @('completed','decisions','files_created','files_modified','lessons_learned','next_actions')) {
        if (Has-Property $Data $Name) {
            $ArrayValue = $Data.PSObject.Properties[$Name].Value
            if (-not ($ArrayValue -is [System.Array])) { [void]$Errors.Add('NOT_ARRAY: ' + $Name) }
        }
    }
    if (Has-Property $Data 'requires_approval') {
        if (-not ($Data.requires_approval -is [bool])) { [void]$Errors.Add('NOT_BOOLEAN: requires_approval') }
    }
}

if ($Errors.Count -gt 0) {
    $QuarantineFile = Join-Path $QuarantineDir ('ONLINE_HANDOFF_invalid_' + $Timestamp + '.json')
    Copy-Item -LiteralPath $Source -Destination $QuarantineFile -Force
    $Rejected = [ordered]@{
        schema_version = 2
        result = 'ONLINE_HANDOFF_REJECTED'
        updated_at = (Get-Date).ToString('o')
        source = $Source
        source_sha256 = Get-Sha256Safe $Source
        accepted_file = $null
        quarantine_file = $QuarantineFile
        errors = @($Errors)
    }
    Write-JsonFile $Rejected $LocalStatus
    Write-JsonFile $Rejected $CloudStatus
    exit 3
}

$AcceptedVersion = Join-Path $InboxDir ('ONLINE_HANDOFF_accepted_' + $Timestamp + '.json')
$AcceptedCurrent = Join-Path $InboxDir 'ONLINE_HANDOFF.accepted.json'
Copy-Item -LiteralPath $Source -Destination $AcceptedVersion -Force
Copy-Item -LiteralPath $Source -Destination $AcceptedCurrent -Force

$Accepted = [ordered]@{
    schema_version = 2
    result = 'ONLINE_HANDOFF_ACCEPTED'
    updated_at = (Get-Date).ToString('o')
    source = $Source
    source_sha256 = Get-Sha256Safe $Source
    accepted_file = $AcceptedVersion
    accepted_current = $AcceptedCurrent
    quarantine_file = $null
    errors = @()
}
Write-JsonFile $Accepted $LocalStatus
Write-JsonFile $Accepted $CloudStatus
exit 0
'@

    $ValidatorContent | Set-Content -LiteralPath $ValidatorPath -Encoding UTF8

    $CmdContent = '@echo off' + [Environment]::NewLine +
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $ValidatorPath + '"' + [Environment]::NewLine +
        'exit /b %ERRORLEVEL%' + [Environment]::NewLine
    $CmdContent | Set-Content -LiteralPath $ValidatorCmdPath -Encoding ASCII

    Copy-Item -LiteralPath $BootstrapPath -Destination (Join-Path $CloudRuntime 'BOOTSTRAP_PACKET.json') -Force
    Copy-Item -LiteralPath $HandoffTemplatePath -Destination (Join-Path $CloudRuntime 'ONLINE_HANDOFF.template.json') -Force

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ValidatorPath -InstallRoot $InstallRoot -CloudRoot $CloudRoot -AllowMissing
    $ValidatorExit = $LASTEXITCODE
    if ($ValidatorExit -ne 0) {
        throw "VALIDATOR_SELFTEST_FAILED: ExitCode=$ValidatorExit"
    }

    $ValidationStatusPath = Join-Path $RuntimeDir 'HANDOFF_VALIDATION_STATUS.json'
    $ValidationState = Get-Content -LiteralPath $ValidationStatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($ValidationState.result -ne 'WAITING_FOR_ONLINE_HANDOFF') {
        throw "VALIDATOR_UNEXPECTED_SELFTEST_RESULT: $($ValidationState.result)"
    }

    $Checks = [ordered]@{
        round1_ready = ($Round1State.status -eq 'ROUND1_PASS_CANDIDATE')
        cloud_home_found = [bool]$CloudRoot
        bootstrap_packet_exists = (Test-Path -LiteralPath $BootstrapPath -PathType Leaf)
        cloud_bootstrap_exists = (Test-Path -LiteralPath (Join-Path $CloudRuntime 'BOOTSTRAP_PACKET.json') -PathType Leaf)
        handoff_template_exists = (Test-Path -LiteralPath $HandoffTemplatePath -PathType Leaf)
        cloud_handoff_template_exists = (Test-Path -LiteralPath (Join-Path $CloudRuntime 'ONLINE_HANDOFF.template.json') -PathType Leaf)
        validator_exists = (Test-Path -LiteralPath $ValidatorPath -PathType Leaf)
        validator_cmd_exists = (Test-Path -LiteralPath $ValidatorCmdPath -PathType Leaf)
        validator_waiting_selftest = ($ValidationState.result -eq 'WAITING_FOR_ONLINE_HANDOFF')
        quarantine_exists = (Test-Path -LiteralPath $QuarantineDir -PathType Container)
        inbox_exists = (Test-Path -LiteralPath $InboxDir -PathType Container)
    }

    $AllPass = $true
    foreach ($Property in $Checks.GetEnumerator()) {
        if (-not [bool]$Property.Value) { $AllPass = $false }
    }
    $Result = if ($AllPass) { 'ROUND2_PASS_CANDIDATE' } else { 'ROUND2_FAIL' }

    $Report = [ordered]@{
        schema_version = 2
        app = $App
        version = $Version
        result = $Result
        started_at = $StartedAt.ToString('o')
        completed_at = (Get-Date).ToString('o')
        computer_name = $env:COMPUTERNAME
        paths = [ordered]@{
            home = $HomeRoot
            install = $InstallRoot
            cloud = $CloudRoot
            cloud_runtime = $CloudRuntime
            bootstrap_packet = $BootstrapPath
            validator = $ValidatorPath
            validator_cmd = $ValidatorCmdPath
        }
        checks = $Checks
        integrity = [ordered]@{
            bootstrap_packet_sha256 = Get-Sha256Safe $BootstrapPath
            handoff_template_sha256 = Get-Sha256Safe $HandoffTemplatePath
            validator_sha256 = Get-Sha256Safe $ValidatorPath
            validator_cmd_sha256 = Get-Sha256Safe $ValidatorCmdPath
        }
        handoff_state = $ValidationState.result
        next_step = 'Round 3: create controlled valid and invalid handoff tests, then verify the full Drive closed loop.'
        approval_state = 'CANDIDATE_NOT_FORMALLY_APPROVED'
    }
    Write-JsonFile $Report $ReportPath

    $Progress = [ordered]@{
        schema_version = 2
        project = 'Lidiya Home Bridge v2'
        current_round = 2
        status = $Result
        active_version = $Version
        updated_at = (Get-Date).ToString('o')
        completed = @(
            'round1 evidence verified',
            'bootstrap packet generated',
            'bootstrap packet copied to cloud Runtime',
            'online handoff template generated',
            'handoff validator installed',
            'missing handoff self-test passed',
            'cloud history preservation enabled'
        )
        pending = @(
            'valid handoff acceptance test',
            'invalid handoff quarantine test',
            'full closed-loop test',
            'GitHub release updater'
        )
        latest_report = $ReportPath
        cloud_report = (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json')
        next_minimum_step = 'Read HOME_BRIDGE_STATUS.json, then deploy Round 3 controlled tests.'
    }
    Write-JsonFile $Progress $ProgressPath

    $Current = [ordered]@{
        schema_version = 1
        app = $App
        active_version = $Version
        active_release = $ReleaseDir
        previous_stable = 'Cloud Bridge v1 (unchanged)'
        status = 'ROUND2_CANDIDATE'
        updated_at = (Get-Date).ToString('o')
    }
    Write-JsonFile $Current (Join-Path $InstallRoot 'current.json')

    Copy-Item -LiteralPath $ReportPath -Destination (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json') -Force
    Copy-Item -LiteralPath $ProgressPath -Destination (Join-Path $CloudRuntime 'ROUND_PROGRESS.json') -Force
    Copy-Item -LiteralPath $ReportPath -Destination (Join-Path $CloudRuntime ('ROUND2_AUDIT_' + $Timestamp + '.json')) -Force

    if (-not $AllPass) { throw 'ROUND2_VERIFICATION_FAILED' }

    Write-Host ''
    Write-Host 'ROUND2 PASS CANDIDATE' -ForegroundColor Green
    Write-Host ('Local report: ' + $ReportPath)
    Write-Host ('Cloud report: ' + (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json'))
    Write-Host ('Bootstrap: ' + (Join-Path $CloudRuntime 'BOOTSTRAP_PACKET.json'))
    exit 0
}
catch {
    $ErrorLine = $_.InvocationInfo.ScriptLineNumber
    $ErrorId = $_.FullyQualifiedErrorId
    $ErrorMessage = $_.Exception.Message
    try {
        if (-not (Test-Path -LiteralPath $LogsDir)) {
            New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
        }
        $Failure = [ordered]@{
            schema_version = 2
            app = $App
            version = $Version
            result = 'ROUND2_FAIL'
            updated_at = (Get-Date).ToString('o')
            error_stage = 'ROUND2_DEPLOY_OR_VERIFY'
            error_line = $ErrorLine
            error_id = $ErrorId
            error_category = $_.CategoryInfo.Category.ToString()
            error_message = $ErrorMessage
            result_report = $ReportPath
        }
        Write-JsonFile $Failure (Join-Path $LogsDir ('ROUND2_ERROR_' + $Timestamp + '.json'))
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
    Write-Host ('ROUND2 FAIL: ' + $ErrorMessage) -ForegroundColor Red
    Write-Host ('ERROR_LINE: ' + $ErrorLine) -ForegroundColor Red
    exit 1
}
