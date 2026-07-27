[CmdletBinding()]
param([string]$InstallRoot='D:\lidiya\0.dev_tools\home_bridge_v2')
$ErrorActionPreference='Stop';Set-StrictMode -Version 2.0
$cpath=Join-Path $InstallRoot 'current.json';$logs=Join-Path $InstallRoot 'logs';if(-not(Test-Path -LiteralPath $logs)){New-Item -ItemType Directory -Path $logs -Force|Out-Null};if(-not(Test-Path -LiteralPath $cpath -PathType Leaf)){throw "CURRENT_NOT_FOUND: $cpath"}
$c=Get-Content -LiteralPath $cpath -Raw -Encoding UTF8|ConvertFrom-Json
foreach($n in @('previous_version','previous_release','previous_sequence')){if(-not($c.PSObject.Properties.Name -contains $n)){throw "ROLLBACK_DATA_MISSING: $n"}}
if(-not(Test-Path -LiteralPath ([string]$c.previous_release) -PathType Container)){throw "PREVIOUS_RELEASE_NOT_FOUND: $($c.previous_release)"}
$r=[ordered]@{schema_version=2;app='Lidiya Home Bridge';active_version=[string]$c.previous_version;active_release=[string]$c.previous_release;update_sequence=[int]$c.previous_sequence;previous_version=[string]$c.active_version;previous_release=[string]$c.active_release;previous_sequence=[int]$c.update_sequence;status='ROLLED_BACK';updated_at=(Get-Date).ToString('o')}
$r|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $cpath -Encoding UTF8
([ordered]@{result='ROLLBACK_PASS';updated_at=(Get-Date).ToString('o');active_version=$r.active_version;active_release=$r.active_release})|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $logs ('ROLLBACK_'+(Get-Date).ToString('yyyyMMdd_HHmmss')+'.json')) -Encoding UTF8
Write-Host ('HOME BRIDGE ROLLED BACK TO: '+$r.active_version) -ForegroundColor Yellow;exit 0
