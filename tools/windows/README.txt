Windows helper scripts

- run_all.ps1
  Starts backend (uvicorn), telegram bot, and named cloudflared tunnel in 3 separate PowerShell windows.

  Example:
    powershell -ExecutionPolicy Bypass -File .\tools\windows\run_all.ps1 -TunnelName madcommandcentre-tunnel

- cloudflared_setup.ps1
  Writes %USERPROFILE%\.cloudflared\config.yml for the tunnel and prints the DNS route command.

  Example:
    powershell -ExecutionPolicy Bypass -File .\tools\windows\cloudflared_setup.ps1 -TunnelUUID 5315da03-4816-426b-84fb-e1290f985e0e -Domain madcommandcentre.org -TunnelName madcommandcentre-tunnel
