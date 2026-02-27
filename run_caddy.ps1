# Запуск Caddy на порту 8080 с Caddyfile в корне проекта
# Требования: caddy.exe рядом с этим файлом или в PATH.
# В отдельном окне PowerShell:
#   ./run_caddy.ps1

$ErrorActionPreference = "Stop"

$caddy = "caddy.exe"
if (-not (Get-Command $caddy -ErrorAction SilentlyContinue)) {
  Write-Host "caddy.exe не найден в PATH. Скачайте Caddy и положите caddy.exe рядом или добавьте в PATH." -ForegroundColor Yellow
}

& $caddy run --config .\Caddyfile --adapter caddyfile
