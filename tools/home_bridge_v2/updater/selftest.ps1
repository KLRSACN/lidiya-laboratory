[CmdletBinding()]
param([string]$ReleaseDir)
$ErrorActionPreference='Stop';Set-StrictMode -Version 2.0
if(-not $ReleaseDir){throw 'RELEASE_DIR_REQUIRED'};$mp=Join-Path $ReleaseDir 'release.json';if(-not(Test-Path -LiteralPath $mp -PathType Leaf)){throw "RELEASE_METADATA_MISSING: $mp"};$m=Get-Content -LiteralPath $mp -Raw -Encoding UTF8|ConvertFrom-Json
foreach($n in @('version','sequence','files')){if(-not($m.PSObject.Properties.Name -contains $n)){throw "RELEASE_METADATA_PROPERTY_MISSING: $n"}}
foreach($f in $m.files){$p=Join-Path $ReleaseDir ([string]$f.path);if(-not(Test-Path -LiteralPath $p -PathType Leaf)){throw "RELEASE_FILE_MISSING: $p"};$h=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant();if($h -ne ([string]$f.sha256).ToLowerInvariant()){throw "RELEASE_FILE_HASH_MISMATCH: $p"}}
Write-Host 'RELEASE SELFTEST PASS' -ForegroundColor Green;exit 0
