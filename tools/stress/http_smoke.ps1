param(
  [string]$Base = "https://madcommandcentre.org"
)

Write-Host "BASE: $Base"

Write-Host "GET /healthz"
Invoke-WebRequest "$Base/healthz" -UseBasicParsing | Select-Object StatusCode, Content

Write-Host "GET /readyz"
Invoke-WebRequest "$Base/readyz" -UseBasicParsing | Select-Object StatusCode, Content

Write-Host "Done"
