param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [string]$TunnelName = "madcommandcentre-tunnel",
  [string]$Host = "127.0.0.1",
  [int]$Port = 8000
)

Write-Host "ProjectRoot: $ProjectRoot"
Write-Host "TunnelName:  $TunnelName"
Write-Host "Server:      http://$Host`:$Port"

# Prefer venv python if present (so new windows use the same environment even without activation)
$VenvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PyExe  = if (Test-Path $VenvPy) { $VenvPy } else { "python" }

# 1) Server (ASGI: HTTP + WebSocket on same port)
$ServerCmd = "Set-Location `"$ProjectRoot`"; & `"$PyExe`" -m uvicorn asgi_realtime:app --host $Host --port $Port"
Start-Process powershell -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-Command",$ServerCmd | Out-Null

# 2) Bot
$BotCmd = "Set-Location `"$ProjectRoot`"; & `"$PyExe`" bot.py"
Start-Process powershell -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-Command",$BotCmd | Out-Null

# 3) Cloudflare Tunnel
$TunnelCmd = "cloudflared tunnel run `"$TunnelName`""
Start-Process powershell -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-Command",$TunnelCmd | Out-Null

Write-Host "Started: server, bot, tunnel (3 windows)."
Write-Host "Tip: if cloudflared isn't found, add it to PATH or run 'where cloudflared' to verify."
