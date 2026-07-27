[CmdletBinding()]
param(
    [string]$HomeRoot = 'D:\lidiya',
    [string]$InstallRoot = 'D:\lidiya\0.dev_tools\home_bridge_v2'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$App = 'Lidiya Home Bridge'
$Version = '2.0.0-alpha.1'
$StartedAt = Get-Date
$Timestamp = $StartedAt.ToString('yyyyMMdd_HHmmss')
$RuntimeDir = Join-Path $InstallRoot 'runtime'
$LogsDir = Join-Path $InstallRoot 'logs'
$ConfigDir = Join-Path $InstallRoot 'config'
$SchemasDir = Join-Path $InstallRoot 'schemas'
$ReleaseDir = Join-Path $InstallRoot ('releases\' + $Version)
$BackupRoot = Join-Path $InstallRoot ('backups\v1_snapshot_' + $Timestamp)
$CloudRoot = $null
$CloudRuntime = $null
$ReportPath = Join-Path $LogsDir ('ROUND1_AUDIT_' + $Timestamp + '.json')
$ProgressPath = Join-Path $RuntimeDir 'ROUND_PROGRESS.json'

function Write-JsonFile {
    param([Parameter(Mandatory=$true)]$Object,[Parameter(Mandatory=$true)][string]$Path)
    $Parent = Split-Path -Parent $Path
    if ($Parent -and -not (Test-Path -LiteralPath $Parent)) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
    $Object | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding UTF8
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

function Find-V1Root {
    $Candidates = @(
        'D:\lidiya\cloud_bridge',
        'D:\lidiya\0.dev_tools\cloud_bridge',
        'D:\lidiya\Lidiya_Cloud_Bridge_v1'
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Container) { return $Candidate }
    }
    return $null
}

try {
    Write-Host '=== Lidiya Home Bridge v2｜Round 1 ===' -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $HomeRoot -PathType Container)) { throw "HOME_ROOT_NOT_FOUND: $HomeRoot" }

    $Directories = @(
        $InstallRoot,$RuntimeDir,$LogsDir,$ConfigDir,$SchemasDir,$ReleaseDir,
        (Join-Path $InstallRoot 'staging'),(Join-Path $InstallRoot 'quarantine'),
        (Join-Path $InstallRoot 'inbox'),(Join-Path $InstallRoot 'outbox'),
        (Join-Path $InstallRoot 'backups'),(Join-Path $InstallRoot 'releases')
    )
    foreach ($Dir in $Directories) { if (-not (Test-Path -LiteralPath $Dir)) { New-Item -ItemType Directory -Path $Dir -Force | Out-Null } }

    $InstalledScript = Join-Path $ReleaseDir 'install_round1.ps1'
    Copy-Item -LiteralPath $MyInvocation.MyCommand.Path -Destination $InstalledScript -Force

    $CloudRoot = Find-CloudHome
    if ($CloudRoot) {
        $CloudRuntime = Join-Path $CloudRoot 'Runtime'
        if (-not (Test-Path -LiteralPath $CloudRuntime)) { New-Item -ItemType Directory -Path $CloudRuntime -Force | Out-Null }
    }

    $V1Root = Find-V1Root
    $V1Files = @('memory_bridge.py','config.json','start_bridge.bat','install_bridge.ps1','uninstall_bridge.ps1')
    $V1Snapshot = @()
    if ($V1Root) {
        New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
        foreach ($Name in $V1Files) {
            $Source = Join-Path $V1Root $Name
            if (Test-Path -LiteralPath $Source -PathType Leaf) {
                $Destination = Join-Path $BackupRoot $Name
                Copy-Item -LiteralPath $Source -Destination $Destination -Force
                $V1Snapshot += [PSCustomObject]@{
                    name = $Name
                    source = $Source
                    backup = $Destination
                    sha256 = Get-Sha256Safe $Destination
                    size_bytes = (Get-Item -LiteralPath $Destination).Length
                }
            }
        }
    }

    $BootstrapSchema = [ordered]@{
        '$schema'='https://json-schema.org/draft/2020-12/schema'
        title='Lidiya Bootstrap Packet'
        type='object'
        required=@('schema_version','packet_id','generated_at','authority','routing','integrity')
        properties=[ordered]@{
            schema_version=[ordered]@{const=2}
            packet_id=[ordered]@{type='string';minLength=1}
            generated_at=[ordered]@{type='string';format='date-time'}
            authority=[ordered]@{type='object'}
            routing=[ordered]@{type='object'}
            integrity=[ordered]@{type='object'}
        }
        additionalProperties=$true
    }
    $HandoffSchema = [ordered]@{
        '$schema'='https://json-schema.org/draft/2020-12/schema'
        title='Lidiya Online Handoff'
        type='object'
        required=@('schema_version','session_id','updated_at','task','completed','decisions','next_actions')
        properties=[ordered]@{
            schema_version=[ordered]@{const=2}
            session_id=[ordered]@{type='string';minLength=1}
            updated_at=[ordered]@{type='string';format='date-time'}
            task=[ordered]@{type='string'}
            completed=[ordered]@{type='array';items=[ordered]@{type='string'}}
            decisions=[ordered]@{type='array';items=[ordered]@{type='string'}}
            files_created=[ordered]@{type='array';items=[ordered]@{type='string'}}
            files_modified=[ordered]@{type='array';items=[ordered]@{type='string'}}
            lessons_learned=[ordered]@{type='array';items=[ordered]@{type='string'}}
            next_actions=[ordered]@{type='array';items=[ordered]@{type='string'}}
            requires_approval=[ordered]@{type='boolean'}
        }
        additionalProperties=$false
    }
    Write-JsonFile $BootstrapSchema (Join-Path $SchemasDir 'bootstrap_packet.schema.json')
    Write-JsonFile $HandoffSchema (Join-Path $SchemasDir 'online_handoff.schema.json')

    $AuthorityMap = [ordered]@{
        schema_version=2
        generated_at=(Get-Date).ToString('o')
        authority=[ordered]@{
            local_home_root=$HomeRoot
            cloud_home_root=$CloudRoot
            local_bridge_v1=$V1Root
            local_bridge_v2=$InstallRoot
            active_release=$ReleaseDir
            local_runtime=$RuntimeDir
            cloud_runtime=$CloudRuntime
            owner='雷博玄'
        }
        boundaries=[ordered]@{
            v1_modified=$false
            windows_task_modified=$false
            files_deleted=$false
            github_main_modified=$false
        }
    }
    $AuthorityPath = Join-Path $ConfigDir 'authority_map.json'
    Write-JsonFile $AuthorityMap $AuthorityPath

    $Current = [ordered]@{
        schema_version=1
        app=$App
        active_version=$Version
        active_release=$ReleaseDir
        previous_stable='Cloud Bridge v1 (unchanged)'
        status='ROUND1_CANDIDATE'
        updated_at=(Get-Date).ToString('o')
    }
    Write-JsonFile $Current (Join-Path $InstallRoot 'current.json')

    $Checks = [ordered]@{
        home_root_exists=(Test-Path -LiteralPath $HomeRoot -PathType Container)
        install_root_exists=(Test-Path -LiteralPath $InstallRoot -PathType Container)
        runtime_exists=(Test-Path -LiteralPath $RuntimeDir -PathType Container)
        staging_exists=(Test-Path -LiteralPath (Join-Path $InstallRoot 'staging') -PathType Container)
        quarantine_exists=(Test-Path -LiteralPath (Join-Path $InstallRoot 'quarantine') -PathType Container)
        authority_map_exists=(Test-Path -LiteralPath $AuthorityPath -PathType Leaf)
        bootstrap_schema_exists=(Test-Path -LiteralPath (Join-Path $SchemasDir 'bootstrap_packet.schema.json') -PathType Leaf)
        handoff_schema_exists=(Test-Path -LiteralPath (Join-Path $SchemasDir 'online_handoff.schema.json') -PathType Leaf)
        cloud_home_found=([bool]$CloudRoot)
        v1_found=([bool]$V1Root)
        v1_snapshot_count=$V1Snapshot.Count
    }
    $LocalPass = $Checks.home_root_exists -and $Checks.install_root_exists -and $Checks.runtime_exists -and $Checks.staging_exists -and $Checks.quarantine_exists -and $Checks.authority_map_exists -and $Checks.bootstrap_schema_exists -and $Checks.handoff_schema_exists
    $Result = if ($LocalPass) { 'ROUND1_PASS_CANDIDATE' } else { 'ROUND1_FAIL' }

    $Report = [ordered]@{
        schema_version=2
        app=$App
        version=$Version
        result=$Result
        started_at=$StartedAt.ToString('o')
        completed_at=(Get-Date).ToString('o')
        computer_name=$env:COMPUTERNAME
        paths=[ordered]@{home=$HomeRoot;install=$InstallRoot;cloud=$CloudRoot;v1=$V1Root;v1_backup=($(if($V1Root){$BackupRoot}else{$null}))}
        checks=$Checks
        v1_snapshot=$V1Snapshot
        integrity=[ordered]@{
            authority_map_sha256=Get-Sha256Safe $AuthorityPath
            bootstrap_schema_sha256=Get-Sha256Safe (Join-Path $SchemasDir 'bootstrap_packet.schema.json')
            handoff_schema_sha256=Get-Sha256Safe (Join-Path $SchemasDir 'online_handoff.schema.json')
            installer_sha256=Get-Sha256Safe $InstalledScript
        }
        next_step='Round 2: generate BOOTSTRAP_PACKET.json and ONLINE_HANDOFF validation flow.'
        approval_state='CANDIDATE_NOT_FORMALLY_APPROVED'
    }
    Write-JsonFile $Report $ReportPath

    $Progress = [ordered]@{
        schema_version=2
        project='Lidiya Home Bridge v2'
        current_round=1
        status=$Result
        active_version=$Version
        updated_at=(Get-Date).ToString('o')
        completed=@('v1 read-only audit','v1 snapshot when found','v2 isolated workspace','authority map','schemas','local evidence report')
        pending=@('online bootstrap packet','online handoff validation','conflict quarantine','full closed-loop test','GitHub release updater')
        latest_report=$ReportPath
        cloud_report=($(if($CloudRuntime){Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json'}else{$null}))
        next_minimum_step='Read HOME_BRIDGE_STATUS.json, then deploy Round 2.'
    }
    Write-JsonFile $Progress $ProgressPath

    if ($CloudRuntime) {
        Copy-Item -LiteralPath $ReportPath -Destination (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json') -Force
        Copy-Item -LiteralPath $ProgressPath -Destination (Join-Path $CloudRuntime 'ROUND_PROGRESS.json') -Force
        Copy-Item -LiteralPath $ReportPath -Destination (Join-Path $CloudRuntime ('ROUND1_AUDIT_' + $Timestamp + '.json')) -Force
    }

    if (-not $LocalPass) { throw 'ROUND1_LOCAL_VERIFICATION_FAILED' }
    Write-Host ''
    Write-Host 'ROUND1 PASS CANDIDATE' -ForegroundColor Green
    Write-Host ('Local report: ' + $ReportPath)
    if ($CloudRuntime) { Write-Host ('Cloud report: ' + (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json')) } else { Write-Host 'Google Drive not found; local evidence was preserved.' -ForegroundColor Yellow }
    exit 0
}
catch {
    $ErrorLine = $_.InvocationInfo.ScriptLineNumber
    $ErrorId = $_.FullyQualifiedErrorId
    $ErrorMessage = $_.Exception.Message
    try {
        if (-not (Test-Path -LiteralPath $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null }
        $Failure = [ordered]@{
            schema_version=2
            app=$App
            version=$Version
            result='ROUND1_FAIL'
            updated_at=(Get-Date).ToString('o')
            error_stage='ROUND1_DEPLOY_OR_VERIFY'
            error_line=$ErrorLine
            error_id=$ErrorId
            error_category=$_.CategoryInfo.Category.ToString()
            error_message=$ErrorMessage
            result_report=$ReportPath
        }
        Write-JsonFile $Failure (Join-Path $LogsDir ('ROUND1_ERROR_' + $Timestamp + '.json'))
        if ($CloudRoot) {
            $CloudRuntime = Join-Path $CloudRoot 'Runtime'
            if (-not (Test-Path -LiteralPath $CloudRuntime)) { New-Item -ItemType Directory -Path $CloudRuntime -Force | Out-Null }
            Write-JsonFile $Failure (Join-Path $CloudRuntime 'HOME_BRIDGE_STATUS.json')
        }
    } catch {}
    Write-Host ('ROUND1 FAIL: ' + $ErrorMessage) -ForegroundColor Red
    Write-Host ('ERROR_LINE=' + $ErrorLine)
    Write-Host ('ERROR_ID=' + $ErrorId)
    exit 1
}
