# Запуск Cloudflare Quick Tunnel (TryCloudflare) для локального Caddy (порт 8080)
# Требования: cloudflared.exe в PATH или рядом с этим файлом.
# В отдельном окне PowerShell:
#   ./run_quicktunnel.ps1

$ErrorActionPreference = "Stop"

$cf = "cloudflared.exe"
if (-not (Get-Command $cf -ErrorAction SilentlyContinue)) {
  Write-Host "cloudflared.exe не найден в PATH. Скачайте cloudflared и добавьте в PATH." -ForegroundColor Yellow
}

& $cf tunnel --url http://localhost:8080
