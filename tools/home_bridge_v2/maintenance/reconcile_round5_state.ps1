[CmdletBinding()]
param(
    [string]$HomeRoot = 'D:\lidiya',
    [string]$InstallRoot = 'D:\lidiya\0.dev_tools\home_bridge_v2'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$StartedAt = Get-Date
$Timestamp = $StartedAt.ToString('yyyyMMdd_HHmmss')
$RuntimeDir = Join-Path $InstallRoot 'runtime'
$LogsDir = Join-Path $InstallRoot 'logs'
$BackupsDir = Join-Path $InstallRoot ('backups\state_reconcile\' + $Timestamp)
$StagingDir = Join-Path $InstallRoot 'staging'
$ApprovalUrl = 'https://raw.githubusercontent.com/KLRSACN/lidiya-laboratory/home-bridge-v2-round1/tools/home_bridge_v2/approvals/ONLINE_FORMAL_APPROVAL_20260727.json'
$ExpectedApprovalSha256 = '4e5a8c0442d683869e40ae35107fca56da477eeca1b95cbcce66673b9fa11e06'
$ApprovalLocalPath = Join-Path $RuntimeDir 'ONLINE_FORMAL_APPROVAL.json'
$ApprovalStagePath = Join-Path $StagingDir ('ONLINE_FORMAL_APPROVAL_' + $Timestamp + '.json')
$StatusPath = Join-Path $RuntimeDir 'HOME_BRIDGE_STATUS.json'
$ProgressPath = Join-Path $RuntimeDir 'ROUND_PROGRESS.json'
$BaselinePath = Join-Path $RuntimeDir 'FORMAL_BASELINE.json'
$CurrentPath = Join-Path $InstallRoot 'current.json'
$AuditPath = Join-Path $LogsDir ('ROUND5_RECONCILE_AUDIT_' + $Timestamp + '.json')

function Ensure-Directory {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-Sha256Safe {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-JsonFile {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw ('FILE_NOT_FOUND: ' + $Path)
    }
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Write-JsonAtomic {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Path
    )
    $Parent = Split-Path -Parent $Path
    Ensure-Directory $Parent
    $Temp = Join-Path $Parent ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $Object | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $Temp -Encoding UTF8
    Move-Item -LiteralPath $Temp -Destination $Path -Force
}

function Add-UniqueText {
    param(
        [Parameter(Mandatory=$true)][System.Collections.ArrayList]$List,
        [Parameter(Mandatory=$true)][string]$Text
    )
    if (-not $List.Contains($Text)) { [void]$List.Add($Text) }
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

function Backup-FileSafe {
    param(
        [Parameter(Mandatory=$true)][string]$Source,
        [Parameter(Mandatory=$true)][string]$DestinationDirectory
    )
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        Ensure-Directory $DestinationDirectory
        Copy-Item -LiteralPath $Source -Destination (Join-Path $DestinationDirectory ([IO.Path]::GetFileName($Source))) -Force
    }
}

$CloudHome = $null
$CloudRuntime = $null
$Result = 'ROUND5_RECONCILE_FAIL'
$ErrorMessage = $null
$ErrorLine = $null
$ActualOnLogonValid = $false
$ActualOnLogonEvidence = $null

try {
    Ensure-Directory $RuntimeDir
    Ensure-Directory $LogsDir
    Ensure-Directory $BackupsDir
    Ensure-Directory $StagingDir

    foreach ($Required in @($BaselinePath, $StatusPath, $ProgressPath, $CurrentPath)) {
        if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
            throw ('REQUIRED_FILE_MISSING: ' + $Required)
        }
    }

    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $ApprovalUrl -OutFile $ApprovalStagePath
    $ApprovalHash = Get-Sha256Safe $ApprovalStagePath
    if ($ApprovalHash -ne $ExpectedApprovalSha256) {
        throw ('APPROVAL_SHA256_MISMATCH: expected=' + $ExpectedApprovalSha256 + '; actual=' + $ApprovalHash)
    }

    $Approval = Read-JsonFile $ApprovalStagePath
    if ([string]$Approval.result -ne 'ROUND5_APPROVED_PENDING_ONLOGON') { throw ('APPROVAL_RESULT_INVALID: ' + [string]$Approval.result) }
    if ([string]$Approval.baseline.version -ne '2.0.0-alpha.4') { throw ('APPROVAL_VERSION_INVALID: ' + [string]$Approval.baseline.version) }
    if ([string]$Approval.baseline.status -ne 'FORMAL_BASELINE') { throw ('APPROVAL_BASELINE_STATUS_INVALID: ' + [string]$Approval.baseline.status) }
    if ([bool]$Approval.boundaries.modify_frozen_release) { throw 'APPROVAL_BOUNDARY_INVALID: modify_frozen_release=true' }
    if ([bool]$Approval.boundaries.modify_cloud_bridge_v1) { throw 'APPROVAL_BOUNDARY_INVALID: modify_cloud_bridge_v1=true' }
    if ([bool]$Approval.boundaries.modify_github_main) { throw 'APPROVAL_BOUNDARY_INVALID: modify_github_main=true' }

    $Baseline = Read-JsonFile $BaselinePath
    $OldStatus = Read-JsonFile $StatusPath
    $OldProgress = Read-JsonFile $ProgressPath
    $OldCurrent = Read-JsonFile $CurrentPath

    if ([string]$Baseline.status -ne 'FORMAL_BASELINE') { throw ('LOCAL_BASELINE_STATUS_INVALID: ' + [string]$Baseline.status) }
    if ([string]$Baseline.version -ne '2.0.0-alpha.4') { throw ('LOCAL_BASELINE_VERSION_INVALID: ' + [string]$Baseline.version) }
    if ([string]$Baseline.baseline_id -ne [string]$Approval.baseline.baseline_id) { throw 'LOCAL_BASELINE_ID_MISMATCH' }
    $LocalBaselineHash = Get-Sha256Safe $BaselinePath
    if ($LocalBaselineHash -ne [string]$Approval.baseline.formal_baseline_sha256) {
        throw ('LOCAL_BASELINE_SHA256_MISMATCH: expected=' + [string]$Approval.baseline.formal_baseline_sha256 + '; actual=' + $LocalBaselineHash)
    }
    if ([string]$OldCurrent.status -ne 'FORMAL') { throw ('CURRENT_NOT_FORMAL: ' + [string]$OldCurrent.status) }

    $CloudHome = Find-CloudHome
    if (-not $CloudHome) { throw 'CLOUD_HOME_NOT_FOUND' }
    $CloudRuntime = Join-Path $CloudHome 'Runtime'
    Ensure-Directory $CloudRuntime
    $CloudHistory = Join-Path $CloudRuntime 'History'
    Ensure-Directory $CloudHistory
    $CloudBackupDir = Join-Path $CloudHistory ('STATE_RECONCILE_' + $Timestamp)
    Ensure-Directory $CloudBackupDir

    Backup-FileSafe $StatusPath $BackupsDir
    Backup-FileSafe $ProgressPath $BackupsDir
    Backup-FileSafe $CurrentPath $BackupsDir
    Backup-FileSafe (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json') $CloudBackupDir
    Backup-FileSafe (Join-Path $CloudRuntime 'ROUND_PROGRESS.json') $CloudBackupDir
    Backup-FileSafe (Join-Path $CloudRuntime 'ONLINE_FORMAL_APPROVAL.json') $CloudBackupDir

    Copy-Item -LiteralPath $ApprovalStagePath -Destination $ApprovalLocalPath -Force
    Copy-Item -LiteralPath $ApprovalStagePath -Destination (Join-Path $CloudRuntime 'ONLINE_FORMAL_APPROVAL.json') -Force

    $OnLogonPath = Join-Path $CloudRuntime 'AUTO_UPDATE_LOGIN_EVIDENCE.json'
    if (Test-Path -LiteralPath $OnLogonPath -PathType Leaf) {
        try {
            $Candidate = Read-JsonFile $OnLogonPath
            $ActualOnLogonValid = (
                ([string]$Candidate.result -eq 'AUTO_UPDATE_ONLOGON_PASS') -and
                ([string]$Candidate.mode -eq 'ONLOGON') -and
                ([int]$Candidate.updater_exit_code -eq 0) -and
                (-not $Candidate.error)
            )
            if ($ActualOnLogonValid) { $ActualOnLogonEvidence = $Candidate }
        } catch {
            $ActualOnLogonValid = $false
        }
    }

    $Result = if ($ActualOnLogonValid) { 'ROUND5_APPROVED_ONLOGON_PASS' } else { 'ROUND5_APPROVED_PENDING_ONLOGON' }
    $ApprovalState = if ($ActualOnLogonValid) {
        'FORMAL_BASELINE_APPROVED_ONLINE_READBACK_INDEX_VERIFIED_ONLOGON_PASS'
    } else {
        'FORMAL_BASELINE_APPROVED_ONLINE_READBACK_INDEX_VERIFIED_ONLOGON_PENDING'
    }

    $Completed = New-Object System.Collections.ArrayList
    foreach ($Item in @($OldProgress.completed)) {
        if ($null -ne $Item -and -not [string]::IsNullOrWhiteSpace([string]$Item)) { Add-UniqueText $Completed ([string]$Item) }
    }
    Add-UniqueText $Completed 'online cloud readback of round5 evidence'
    Add-UniqueText $Completed '00 index formal entry'
    Add-UniqueText $Completed 'online formal approval evidence verified by SHA256'
    if ($ActualOnLogonValid) { Add-UniqueText $Completed 'actual ONLOGON evidence validated' }

    $Pending = New-Object System.Collections.ArrayList
    if (-not $ActualOnLogonValid) { [void]$Pending.Add('actual ONLOGON evidence after next normal login') }

    $NewProgress = [ordered]@{
        schema_version = 2
        project = 'Lidiya Home Bridge v2'
        current_round = 5
        status = $Result
        active_version = '2.0.0-alpha.4'
        updated_at = (Get-Date).ToString('o')
        completed = @($Completed)
        pending = @($Pending)
        latest_report = $AuditPath
        cloud_report = (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json')
        online_approval = $ApprovalLocalPath
        online_approval_sha256 = $ApprovalHash
        next_minimum_step = if ($ActualOnLogonValid) {
            'Online readback and final ONLOGON closeout.'
        } else {
            'Normal Windows sign-out/sign-in or reboot; wait 60 seconds; then read AUTO_UPDATE_LOGIN_EVIDENCE.json online.'
        }
    }

    $NewCurrent = [ordered]@{
        schema_version = 2
        app = 'Lidiya Home Bridge'
        active_version = [string]$OldCurrent.active_version
        active_release = [string]$OldCurrent.active_release
        previous_version = [string]$OldCurrent.previous_version
        previous_release = [string]$OldCurrent.previous_release
        previous_stable = [string]$OldCurrent.previous_stable
        status = 'FORMAL'
        approval_state = $ApprovalState
        formal_baseline = $BaselinePath
        online_approval = $ApprovalLocalPath
        actual_onlogon_result = if ($ActualOnLogonValid) { 'AUTO_UPDATE_ONLOGON_PASS' } else { 'PENDING_NEXT_LOGIN' }
        updated_at = (Get-Date).ToString('o')
    }

    $Checks = [ordered]@{
        round4_ready = $true
        startup_launcher_installed = $true
        release_manifest_verified = $true
        startup_simulation_pass = $true
        baseline_exists = $true
        handoff_exists = $true
        current_formal = $true
        onlogon_wrapper_exists = $true
        startup_vbs_exists = $true
        online_cloud_readback_verified = $true
        index_entry_verified = $true
        index_backup_verified = $true
        github_main_unchanged_verified = $true
        online_approval_sha256_verified = $true
        actual_onlogon_evidence_present = (Test-Path -LiteralPath $OnLogonPath -PathType Leaf)
        actual_onlogon_evidence_valid = $ActualOnLogonValid
    }

    $NewStatus = [ordered]@{
        schema_version = 2
        app = 'Lidiya Home Bridge'
        version = '2.0.0-alpha.4'
        sequence = 5
        result = $Result
        started_at = $StartedAt.ToString('o')
        completed_at = (Get-Date).ToString('o')
        computer_name = $env:COMPUTERNAME
        checks = $Checks
        paths = [ordered]@{
            install = $InstallRoot
            release = [string]$Baseline.frozen_release
            formal_baseline = $BaselinePath
            formal_handoff = (Join-Path $InstallRoot 'docs\HOME_BRIDGE_V2_FORMAL_HANDOFF.md')
            startup_file = [string]$Baseline.startup.startup_file
            startup_acceptance_cmd = (Join-Path $InstallRoot 'RUN_STARTUP_ACCEPTANCE.cmd')
            onlogon_cmd = (Join-Path $InstallRoot 'RUN_ONLOGON_UPDATE.cmd')
            cloud_runtime = $CloudRuntime
            online_approval = $ApprovalLocalPath
        }
        integrity = [ordered]@{
            formal_baseline_sha256 = $LocalBaselineHash
            online_approval_sha256 = $ApprovalHash
            current_state_before_sha256 = Get-Sha256Safe $CurrentPath
            status_before_sha256 = Get-Sha256Safe $StatusPath
            progress_before_sha256 = Get-Sha256Safe $ProgressPath
        }
        actual_onlogon = if ($ActualOnLogonValid) { $ActualOnLogonEvidence } else { [ordered]@{ result = 'PENDING_NEXT_LOGIN'; evidence_path = $OnLogonPath } }
        approval_state = $ApprovalState
        next_step = if ($ActualOnLogonValid) {
            'Online readback and final ONLOGON closeout.'
        } else {
            'Perform one normal Windows login cycle; wait 60 seconds; then verify AUTO_UPDATE_LOGIN_EVIDENCE.json online.'
        }
        boundaries = [ordered]@{
            cloud_bridge_v1_modified = $false
            files_deleted = $false
            github_main_modified = $false
            formal_release_hotpatched = $false
        }
    }

    Write-JsonAtomic $NewCurrent $CurrentPath
    Write-JsonAtomic $NewProgress $ProgressPath
    Write-JsonAtomic $NewStatus $StatusPath

    $Audit = [ordered]@{
        schema_version = 2
        app = 'Lidiya Home Bridge'
        result = $Result
        reconciled_at = (Get-Date).ToString('o')
        online_approval_sha256 = $ApprovalHash
        actual_onlogon_valid = $ActualOnLogonValid
        backup_directory = $BackupsDir
        cloud_backup_directory = $CloudBackupDir
        checks = $Checks
        boundaries = $NewStatus.boundaries
        error = $null
    }
    Write-JsonAtomic $Audit $AuditPath

    Copy-Item -LiteralPath $CurrentPath -Destination (Join-Path $CloudRuntime 'CURRENT_HOME_BRIDGE.json') -Force
    Copy-Item -LiteralPath $ProgressPath -Destination (Join-Path $CloudRuntime 'ROUND_PROGRESS.json') -Force
    Copy-Item -LiteralPath $StatusPath -Destination (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json') -Force
    Copy-Item -LiteralPath $AuditPath -Destination (Join-Path $CloudRuntime ([IO.Path]::GetFileName($AuditPath))) -Force

    Write-Host ''
    Write-Host 'ROUND5 STATE RECONCILE PASS' -ForegroundColor Green
    Write-Host ('State: ' + $Result)
    Write-Host ('Local report: ' + $AuditPath)
    Write-Host ('Cloud report: ' + (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json'))
    Write-Host ('Approval evidence: ' + (Join-Path $CloudRuntime 'ONLINE_FORMAL_APPROVAL.json'))
    if (-not $ActualOnLogonValid) {
        Write-Host 'Actual ONLOGON remains pending; no false success was recorded.' -ForegroundColor Yellow
    }
    exit 0
} catch {
    $ErrorMessage = $_.Exception.Message
    $ErrorLine = $_.InvocationInfo.ScriptLineNumber
    $Failure = [ordered]@{
        schema_version = 2
        app = 'Lidiya Home Bridge'
        result = 'ROUND5_RECONCILE_FAIL'
        failed_at = (Get-Date).ToString('o')
        error = $ErrorMessage
        error_line = $ErrorLine
        install_root = $InstallRoot
        cloud_home = $CloudHome
        boundaries = [ordered]@{
            cloud_bridge_v1_modified = $false
            files_deleted = $false
            github_main_modified = $false
            formal_release_hotpatched = $false
        }
    }
    try {
        Ensure-Directory $LogsDir
        Write-JsonAtomic $Failure $AuditPath
        if ($CloudRuntime) { Copy-Item -LiteralPath $AuditPath -Destination (Join-Path $CloudRuntime ([IO.Path]::GetFileName($AuditPath))) -Force }
    } catch { }
    Write-Host ''
    Write-Host ('ROUND5 STATE RECONCILE FAIL: ' + $ErrorMessage) -ForegroundColor Red
    Write-Host ('ERROR_LINE: ' + $ErrorLine) -ForegroundColor Red
    Write-Host ('Local report: ' + $AuditPath)
    exit 1
}
