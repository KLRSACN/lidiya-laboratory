[CmdletBinding()]
param(
    [string]$HomeRoot = 'D:\lidiya',
    [string]$InstallRoot = 'D:\lidiya\0.dev_tools\home_bridge_v2'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$App = 'Lidiya Home Bridge'
$Version = '2.0.0-alpha.3'
$StartedAt = Get-Date
$Timestamp = $StartedAt.ToString('yyyyMMdd_HHmmss')

$RuntimeDir = Join-Path $InstallRoot 'runtime'
$LogsDir = Join-Path $InstallRoot 'logs'
$InboxDir = Join-Path $InstallRoot 'inbox'
$QuarantineDir = Join-Path $InstallRoot 'quarantine'
$ReleaseDir = Join-Path $InstallRoot ('releases\' + $Version)
$ProgressPath = Join-Path $RuntimeDir 'ROUND_PROGRESS.json'
$BootstrapPath = Join-Path $RuntimeDir 'BOOTSTRAP_PACKET.json'
$ReportPath = Join-Path $LogsDir ('ROUND3_AUDIT_' + $Timestamp + '.json')
$AckPath = Join-Path $RuntimeDir 'CLOSED_LOOP_ACK.json'

function Write-JsonFile {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Path
    )
    $Parent = Split-Path -Parent $Path
    if ($Parent -and -not (Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    $Object | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Path -Encoding UTF8
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

function Copy-ToHistory {
    param(
        [string]$Source,
        [string]$HistoryDir,
        [string]$Label
    )
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        $Extension = [System.IO.Path]::GetExtension($Source)
        $Name = $Label + '_' + $Timestamp + $Extension
        Copy-Item -LiteralPath $Source -Destination (Join-Path $HistoryDir $Name) -Force
    }
}

try {
    Write-Host '=== Lidiya Home Bridge v2｜Round 3 ===' -ForegroundColor Cyan

    if (-not (Test-Path -LiteralPath $HomeRoot -PathType Container)) {
        throw "HOME_ROOT_NOT_FOUND: $HomeRoot"
    }

    foreach ($Dir in @($InstallRoot,$RuntimeDir,$LogsDir,$InboxDir,$QuarantineDir,$ReleaseDir)) {
        if (-not (Test-Path -LiteralPath $Dir)) {
            New-Item -ItemType Directory -Path $Dir -Force | Out-Null
        }
    }

    if (-not (Test-Path -LiteralPath $ProgressPath -PathType Leaf)) {
        throw "ROUND2_PROGRESS_NOT_FOUND: $ProgressPath"
    }
    $Round2State = Get-Content -LiteralPath $ProgressPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Round2State.status -ne 'ROUND2_PASS_CANDIDATE') {
        throw "ROUND2_NOT_READY: $($Round2State.status)"
    }

    if (-not (Test-Path -LiteralPath $BootstrapPath -PathType Leaf)) {
        throw "BOOTSTRAP_PACKET_NOT_FOUND: $BootstrapPath"
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

    $ValidatorPath = Join-Path $InstallRoot 'releases\2.0.0-alpha.2\validate_online_handoff.ps1'
    if (-not (Test-Path -LiteralPath $ValidatorPath -PathType Leaf)) {
        throw "VALIDATOR_NOT_FOUND: $ValidatorPath"
    }

    $InstalledScript = Join-Path $ReleaseDir 'install_round3.ps1'
    Copy-Item -LiteralPath $MyInvocation.MyCommand.Path -Destination $InstalledScript -Force

    $CloudHandoff = Join-Path $CloudRuntime 'ONLINE_HANDOFF.json'
    $CloudValidation = Join-Path $CloudRuntime 'HANDOFF_VALIDATION_STATUS.json'
    $LocalValidation = Join-Path $RuntimeDir 'HANDOFF_VALIDATION_STATUS.json'
    $AcceptedCurrent = Join-Path $InboxDir 'ONLINE_HANDOFF.accepted.json'

    Copy-ToHistory (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json') $CloudHistory 'HOME_BRIDGE_STATUS_before_round3'
    Copy-ToHistory (Join-Path $CloudRuntime 'ROUND_PROGRESS.json') $CloudHistory 'ROUND_PROGRESS_before_round3'
    Copy-ToHistory (Join-Path $CloudRuntime 'BOOTSTRAP_PACKET.json') $CloudHistory 'BOOTSTRAP_PACKET_before_round3'
    Copy-ToHistory $CloudValidation $CloudHistory 'HANDOFF_VALIDATION_STATUS_before_round3'
    Copy-ToHistory $CloudHandoff $CloudHistory 'ONLINE_HANDOFF_before_round3'

    $ValidHandoff = [ordered]@{
        schema_version = 2
        session_id = ('ROUND3_VALID_' + $Timestamp)
        updated_at = (Get-Date).ToString('o')
        task = 'Lidiya Home Bridge v2 closed-loop acceptance test'
        completed = @(
            'online-style handoff written into cloud Runtime',
            'local validator invoked',
            'accepted copy expected in local inbox'
        )
        decisions = @(
            'Cloud Bridge v1 remains unchanged',
            'Home Bridge v2 owns routing, validation and evidence only'
        )
        files_created = @('Runtime/ONLINE_HANDOFF.json')
        files_modified = @('Runtime/HANDOFF_VALIDATION_STATUS.json')
        lessons_learned = @('A valid schema-v2 handoff must be accepted without manual file movement.')
        next_actions = @('Run invalid handoff quarantine test.')
        requires_approval = $false
    }
    Write-JsonFile $ValidHandoff $CloudHandoff
    $ValidSourceSha = Get-Sha256Safe $CloudHandoff

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ValidatorPath -InstallRoot $InstallRoot -CloudRoot $CloudRoot
    $ValidExit = $LASTEXITCODE
    if ($ValidExit -ne 0) { throw "VALID_HANDOFF_VALIDATOR_FAILED: ExitCode=$ValidExit" }
    if (-not (Test-Path -LiteralPath $LocalValidation -PathType Leaf)) { throw 'VALID_STATUS_NOT_CREATED' }
    $ValidStatus = Get-Content -LiteralPath $LocalValidation -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($ValidStatus.result -ne 'ONLINE_HANDOFF_ACCEPTED') {
        throw "VALID_HANDOFF_NOT_ACCEPTED: $($ValidStatus.result)"
    }
    if (-not (Test-Path -LiteralPath $AcceptedCurrent -PathType Leaf)) { throw 'ACCEPTED_CURRENT_NOT_CREATED' }
    $AcceptedSha = Get-Sha256Safe $AcceptedCurrent
    if ($AcceptedSha -ne $ValidSourceSha) { throw 'VALID_HANDOFF_SHA_MISMATCH' }

    $ValidStatusEvidence = Join-Path $LogsDir ('ROUND3_VALID_STATUS_' + $Timestamp + '.json')
    Copy-Item -LiteralPath $LocalValidation -Destination $ValidStatusEvidence -Force
    Copy-Item -LiteralPath $CloudHandoff -Destination (Join-Path $CloudHistory ('ONLINE_HANDOFF_valid_' + $Timestamp + '.json')) -Force
    Copy-Item -LiteralPath $CloudValidation -Destination (Join-Path $CloudHistory ('HANDOFF_VALIDATION_valid_' + $Timestamp + '.json')) -Force

    $InvalidHandoff = [ordered]@{
        schema_version = 1
        session_id = ''
        updated_at = ''
        task = ''
        completed = 'NOT_AN_ARRAY'
        decisions = @()
        next_actions = @()
        requires_approval = 'NOT_A_BOOLEAN'
    }
    Write-JsonFile $InvalidHandoff $CloudHandoff
    $InvalidSourceSha = Get-Sha256Safe $CloudHandoff

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ValidatorPath -InstallRoot $InstallRoot -CloudRoot $CloudRoot
    $InvalidExit = $LASTEXITCODE
    if ($InvalidExit -ne 3) { throw "INVALID_HANDOFF_UNEXPECTED_EXIT: ExitCode=$InvalidExit" }
    $InvalidStatus = Get-Content -LiteralPath $LocalValidation -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($InvalidStatus.result -ne 'ONLINE_HANDOFF_REJECTED') {
        throw "INVALID_HANDOFF_NOT_REJECTED: $($InvalidStatus.result)"
    }
    if ([string]::IsNullOrWhiteSpace([string]$InvalidStatus.quarantine_file)) {
        throw 'QUARANTINE_PATH_MISSING'
    }
    if (-not (Test-Path -LiteralPath ([string]$InvalidStatus.quarantine_file) -PathType Leaf)) {
        throw "QUARANTINE_FILE_NOT_FOUND: $($InvalidStatus.quarantine_file)"
    }
    $QuarantineSha = Get-Sha256Safe ([string]$InvalidStatus.quarantine_file)
    if ($QuarantineSha -ne $InvalidSourceSha) { throw 'QUARANTINE_SHA_MISMATCH' }

    $InvalidStatusEvidence = Join-Path $LogsDir ('ROUND3_INVALID_STATUS_' + $Timestamp + '.json')
    Copy-Item -LiteralPath $LocalValidation -Destination $InvalidStatusEvidence -Force
    Copy-Item -LiteralPath $CloudHandoff -Destination (Join-Path $CloudHistory ('ONLINE_HANDOFF_invalid_' + $Timestamp + '.json')) -Force
    Copy-Item -LiteralPath $CloudValidation -Destination (Join-Path $CloudHistory ('HANDOFF_VALIDATION_invalid_' + $Timestamp + '.json')) -Force

    $FinalHandoff = [ordered]@{
        schema_version = 2
        session_id = ('ROUND3_FINAL_' + $Timestamp)
        updated_at = (Get-Date).ToString('o')
        task = 'Lidiya Home Bridge v2 closed-loop completion handoff'
        completed = @(
            'valid handoff accepted',
            'invalid handoff rejected',
            'invalid handoff preserved in quarantine',
            'cloud Runtime restored to a valid accepted handoff'
        )
        decisions = @(
            'Keep Cloud Bridge v1 as the transport layer',
            'Promote Home Bridge v2 only after online cloud readback confirms this report'
        )
        files_created = @(
            'Runtime/CLOSED_LOOP_ACK.json',
            'Runtime/ONLINE_HANDOFF.json'
        )
        files_modified = @(
            'Runtime/HOME_BRIDGE_STATUS.json',
            'Runtime/ROUND_PROGRESS.json',
            'Runtime/BOOTSTRAP_PACKET.json',
            'Runtime/HANDOFF_VALIDATION_STATUS.json'
        )
        lessons_learned = @(
            'Valid schema-v2 handoffs are accepted and copied into the local inbox.',
            'Malformed or schema-invalid handoffs are rejected and preserved in quarantine.'
        )
        next_actions = @('Online Lidiya reads cloud evidence and formally approves Round 3.')
        requires_approval = $true
    }
    Write-JsonFile $FinalHandoff $CloudHandoff
    $FinalSourceSha = Get-Sha256Safe $CloudHandoff

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ValidatorPath -InstallRoot $InstallRoot -CloudRoot $CloudRoot
    $FinalExit = $LASTEXITCODE
    if ($FinalExit -ne 0) { throw "FINAL_HANDOFF_VALIDATOR_FAILED: ExitCode=$FinalExit" }
    $FinalStatus = Get-Content -LiteralPath $LocalValidation -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($FinalStatus.result -ne 'ONLINE_HANDOFF_ACCEPTED') {
        throw "FINAL_HANDOFF_NOT_ACCEPTED: $($FinalStatus.result)"
    }
    $FinalAcceptedSha = Get-Sha256Safe $AcceptedCurrent
    if ($FinalAcceptedSha -ne $FinalSourceSha) { throw 'FINAL_ACCEPTED_SHA_MISMATCH' }

    $Bootstrap = Get-Content -LiteralPath $BootstrapPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $Bootstrap.packet_id = ('BOOTSTRAP_' + $Timestamp)
    $Bootstrap.generated_at = (Get-Date).ToString('o')
    $Bootstrap.authority.active_version = $Version
    $Bootstrap.authority.approval_state = 'ROUND3_CANDIDATE_NOT_FORMALLY_APPROVED'
    $Bootstrap.routing.current_round = 3
    $Bootstrap.routing.next_action = 'Read HOME_BRIDGE_STATUS.json, CLOSED_LOOP_ACK.json and HANDOFF_VALIDATION_STATUS.json; formally approve Round 3 after cloud readback.'
    $Bootstrap.state.completed = @(
        'v1 read-only audit and snapshot',
        'v2 isolated workspace and schemas',
        'bootstrap packet and validator',
        'valid handoff acceptance test',
        'invalid handoff quarantine test',
        'final accepted handoff restoration'
    )
    $Bootstrap.state.pending = @(
        'online cloud evidence readback and formal approval',
        'GitHub release updater and rollback'
    )
    Write-JsonFile $Bootstrap $BootstrapPath
    Copy-Item -LiteralPath $BootstrapPath -Destination (Join-Path $CloudRuntime 'BOOTSTRAP_PACKET.json') -Force

    $Checks = [ordered]@{
        round2_ready = ($Round2State.status -eq 'ROUND2_PASS_CANDIDATE')
        cloud_home_found = [bool]$CloudRoot
        valid_validator_exit_zero = ($ValidExit -eq 0)
        valid_handoff_accepted = ($ValidStatus.result -eq 'ONLINE_HANDOFF_ACCEPTED')
        valid_sha_match = ($AcceptedSha -eq $ValidSourceSha)
        invalid_validator_exit_three = ($InvalidExit -eq 3)
        invalid_handoff_rejected = ($InvalidStatus.result -eq 'ONLINE_HANDOFF_REJECTED')
        quarantine_file_exists = (Test-Path -LiteralPath ([string]$InvalidStatus.quarantine_file) -PathType Leaf)
        quarantine_sha_match = ($QuarantineSha -eq $InvalidSourceSha)
        final_validator_exit_zero = ($FinalExit -eq 0)
        final_handoff_accepted = ($FinalStatus.result -eq 'ONLINE_HANDOFF_ACCEPTED')
        final_sha_match = ($FinalAcceptedSha -eq $FinalSourceSha)
        cloud_bootstrap_exists = (Test-Path -LiteralPath (Join-Path $CloudRuntime 'BOOTSTRAP_PACKET.json') -PathType Leaf)
        cloud_online_handoff_exists = (Test-Path -LiteralPath $CloudHandoff -PathType Leaf)
        cloud_validation_status_exists = (Test-Path -LiteralPath $CloudValidation -PathType Leaf)
    }

    $AllPass = $true
    foreach ($Property in $Checks.GetEnumerator()) {
        if (-not [bool]$Property.Value) { $AllPass = $false }
    }
    $Result = if ($AllPass) { 'ROUND3_PASS_CANDIDATE' } else { 'ROUND3_FAIL' }

    $Ack = [ordered]@{
        schema_version = 2
        app = $App
        version = $Version
        result = $Result
        updated_at = (Get-Date).ToString('o')
        valid_test = [ordered]@{
            source_sha256 = $ValidSourceSha
            accepted_sha256 = $AcceptedSha
            result = $ValidStatus.result
            status_evidence = $ValidStatusEvidence
        }
        invalid_test = [ordered]@{
            source_sha256 = $InvalidSourceSha
            quarantine_sha256 = $QuarantineSha
            result = $InvalidStatus.result
            quarantine_file = [string]$InvalidStatus.quarantine_file
            errors = @($InvalidStatus.errors)
            status_evidence = $InvalidStatusEvidence
        }
        final_state = [ordered]@{
            source_sha256 = $FinalSourceSha
            accepted_sha256 = $FinalAcceptedSha
            result = $FinalStatus.result
            online_handoff = $CloudHandoff
            validation_status = $CloudValidation
        }
        approval_state = 'CANDIDATE_WAITING_FOR_ONLINE_CLOUD_READBACK'
    }
    Write-JsonFile $Ack $AckPath
    Copy-Item -LiteralPath $AckPath -Destination (Join-Path $CloudRuntime 'CLOSED_LOOP_ACK.json') -Force

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
            online_handoff = $CloudHandoff
            validation_status = $CloudValidation
            closed_loop_ack = (Join-Path $CloudRuntime 'CLOSED_LOOP_ACK.json')
            quarantine_file = [string]$InvalidStatus.quarantine_file
            accepted_current = $AcceptedCurrent
        }
        checks = $Checks
        integrity = [ordered]@{
            installer_sha256 = Get-Sha256Safe $InstalledScript
            bootstrap_packet_sha256 = Get-Sha256Safe $BootstrapPath
            final_handoff_sha256 = $FinalSourceSha
            final_accepted_sha256 = $FinalAcceptedSha
            closed_loop_ack_sha256 = Get-Sha256Safe $AckPath
        }
        next_step = 'Online cloud readback and formal Round 3 approval; then build GitHub release updater and rollback.'
        approval_state = 'CANDIDATE_NOT_FORMALLY_APPROVED'
    }
    Write-JsonFile $Report $ReportPath

    $Progress = [ordered]@{
        schema_version = 2
        project = 'Lidiya Home Bridge v2'
        current_round = 3
        status = $Result
        active_version = $Version
        updated_at = (Get-Date).ToString('o')
        completed = @(
            'round1 evidence verified',
            'round2 bootstrap and validator verified',
            'valid online handoff acceptance test passed',
            'invalid online handoff quarantine test passed',
            'final valid handoff restored and accepted',
            'closed-loop evidence written to cloud Runtime'
        )
        pending = @(
            'online cloud evidence readback and formal approval',
            'GitHub release updater and rollback'
        )
        latest_report = $ReportPath
        cloud_report = (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json')
        next_minimum_step = 'Online Lidiya reads HOME_BRIDGE_STATUS.json and CLOSED_LOOP_ACK.json.'
    }
    Write-JsonFile $Progress $ProgressPath

    $Current = [ordered]@{
        schema_version = 1
        app = $App
        active_version = $Version
        active_release = $ReleaseDir
        previous_stable = 'Cloud Bridge v1 (unchanged)'
        previous_candidate = 'Home Bridge v2 2.0.0-alpha.2'
        status = 'ROUND3_CANDIDATE'
        updated_at = (Get-Date).ToString('o')
    }
    Write-JsonFile $Current (Join-Path $InstallRoot 'current.json')

    Copy-Item -LiteralPath $ReportPath -Destination (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json') -Force
    Copy-Item -LiteralPath $ProgressPath -Destination (Join-Path $CloudRuntime 'ROUND_PROGRESS.json') -Force
    Copy-Item -LiteralPath $ReportPath -Destination (Join-Path $CloudRuntime ('ROUND3_AUDIT_' + $Timestamp + '.json')) -Force
    Copy-Item -LiteralPath $LocalValidation -Destination $CloudValidation -Force

    if (-not $AllPass) { throw 'ROUND3_VERIFICATION_FAILED' }

    Write-Host ''
    Write-Host 'ROUND3 PASS CANDIDATE' -ForegroundColor Green
    Write-Host ('Local report: ' + $ReportPath)
    Write-Host ('Cloud report: ' + (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json'))
    Write-Host ('Closed-loop evidence: ' + (Join-Path $CloudRuntime 'CLOSED_LOOP_ACK.json'))
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
            result = 'ROUND3_FAIL'
            updated_at = (Get-Date).ToString('o')
            error_stage = 'ROUND3_CLOSED_LOOP_TEST'
            error_line = $ErrorLine
            error_id = $ErrorId
            error_category = $_.CategoryInfo.Category.ToString()
            error_message = $ErrorMessage
            result_report = $ReportPath
        }
        Write-JsonFile $Failure (Join-Path $LogsDir ('ROUND3_ERROR_' + $Timestamp + '.json'))
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
    Write-Host ('ROUND3 FAIL: ' + $ErrorMessage) -ForegroundColor Red
    Write-Host ('ERROR_LINE: ' + $ErrorLine) -ForegroundColor Red
    exit 1
}
