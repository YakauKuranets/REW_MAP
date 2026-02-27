param(
  [Parameter(Mandatory=$true)][string]$TunnelUUID,
  [Parameter(Mandatory=$true)][string]$Domain,
  [string]$TunnelName = "madcommandcentre-tunnel",
  [string]$LocalService = "http://127.0.0.1:8000"
)

$cfgDir = Join-Path $env:USERPROFILE ".cloudflared"
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null

$cred = Join-Path $cfgDir ($TunnelUUID + ".json")
$cfg  = Join-Path $cfgDir "config.yml"

@"
tunnel: $TunnelUUID
credentials-file: $cred
edge-ip-version: 4
protocol: http2

ingress:
  - hostname: $Domain
    service: $LocalService
  - service: http_status:404
"@ | Set-Content -Encoding utf8 $cfg

Write-Host "Written config: $cfg"
Write-Host "If credentials file is missing, run: cloudflared tunnel login"
Write-Host ""
Write-Host "Next step (creates DNS route):"
Write-Host "  cloudflared tunnel route dns $TunnelName $Domain"
