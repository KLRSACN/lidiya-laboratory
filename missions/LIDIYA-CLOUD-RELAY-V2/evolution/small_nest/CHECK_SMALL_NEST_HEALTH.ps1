param(
  [int]$Port = 8765
)
$ErrorActionPreference = "Stop"
$uri = "http://127.0.0.1:$Port/health"
$result = Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec 5
$result | ConvertTo-Json -Depth 8
