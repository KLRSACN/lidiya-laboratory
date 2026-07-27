[CmdletBinding()]
param([string]$InstallRoot='D:\lidiya\0.dev_tools\home_bridge_v2',[string]$ManifestUrl='',[string]$ManifestPath='')
$ErrorActionPreference='Stop';Set-StrictMode -Version 2.0
$ts=(Get-Date).ToString('yyyyMMdd_HHmmss');$st=Join-Path $InstallRoot 'staging';$lg=Join-Path $InstallRoot 'logs';$cur=Join-Path $InstallRoot 'current.json'
foreach($d in @($st,$lg,(Join-Path $InstallRoot 'releases'))){if(-not(Test-Path -LiteralPath $d)){New-Item -ItemType Directory -Path $d -Force|Out-Null}}
function WJ($o,$p){$o|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $p -Encoding UTF8};function GH($p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
if(-not(Test-Path -LiteralPath $cur -PathType Leaf)){throw "CURRENT_NOT_FOUND: $cur"};$c=Get-Content -LiteralPath $cur -Raw -Encoding UTF8|ConvertFrom-Json
$ml=Join-Path $st ('manifest_'+$ts+'.json')
if($ManifestPath){Copy-Item -LiteralPath $ManifestPath -Destination $ml -Force}else{if(-not $ManifestUrl){throw 'MANIFEST_SOURCE_MISSING'};[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -UseBasicParsing -Uri $ManifestUrl -OutFile $ml}
$m=Get-Content -LiteralPath $ml -Raw -Encoding UTF8|ConvertFrom-Json
foreach($n in @('version','sequence','payload_sha256')){if(-not($m.PSObject.Properties.Name -contains $n)){throw "MANIFEST_MISSING: $n"}}
$cs=if($c.PSObject.Properties.Name -contains 'update_sequence'){[int]$c.update_sequence}else{0};$rs=[int]$m.sequence;$status=Join-Path $lg ('UPDATE_CHECK_'+$ts+'.json')
if($rs -le $cs){WJ ([ordered]@{result='UP_TO_DATE';checked_at=(Get-Date).ToString('o');current_version=$c.active_version;current_sequence=$cs;remote_version=$m.version;remote_sequence=$rs}) $status;Write-Host 'HOME BRIDGE UP TO DATE' -ForegroundColor Green;exit 0}
$pl=Join-Path $st ('payload_'+$m.version+'_'+$ts+'.ps1')
if($m.PSObject.Properties.Name -contains 'payload_path' -and $m.payload_path){Copy-Item -LiteralPath ([string]$m.payload_path) -Destination $pl -Force}elseif($m.PSObject.Properties.Name -contains 'payload_url' -and $m.payload_url){[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -UseBasicParsing -Uri ([string]$m.payload_url) -OutFile $pl}else{throw 'PAYLOAD_SOURCE_MISSING'}
$h=GH $pl;if($h -ne ([string]$m.payload_sha256).ToLowerInvariant()){throw "PAYLOAD_SHA256_MISMATCH: $h"};$snap=Join-Path $st ('current_before_'+$ts+'.json');Copy-Item -LiteralPath $cur -Destination $snap -Force
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $pl -InstallRoot $InstallRoot -UpdatePayloadMode;if($LASTEXITCODE -ne 0){throw "PAYLOAD_INSTALL_FAILED: $LASTEXITCODE"}
$nr=Join-Path (Join-Path $InstallRoot 'releases') ([string]$m.version);$rm=Join-Path $nr 'release.json';if(-not(Test-Path -LiteralPath $rm -PathType Leaf)){throw "RELEASE_METADATA_MISSING: $rm"};$r=Get-Content -LiteralPath $rm -Raw -Encoding UTF8|ConvertFrom-Json
if([string]$r.version -ne [string]$m.version -or [int]$r.sequence -ne $rs){throw 'RELEASE_METADATA_MISMATCH'}
WJ ([ordered]@{schema_version=2;app='Lidiya Home Bridge';active_version=[string]$m.version;active_release=$nr;update_sequence=$rs;previous_version=[string]$c.active_version;previous_release=[string]$c.active_release;previous_sequence=$cs;status='UPDATED_CANDIDATE';updated_at=(Get-Date).ToString('o');rollback_snapshot=$snap}) $cur
WJ ([ordered]@{result='UPDATE_APPLIED';updated_at=(Get-Date).ToString('o');from_version=$c.active_version;to_version=$m.version;payload_sha256=$h;release=$nr}) $status
Write-Host ('HOME BRIDGE UPDATED: '+$m.version) -ForegroundColor Green;exit 0
