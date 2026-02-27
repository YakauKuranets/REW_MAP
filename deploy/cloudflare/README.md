# Deploy: Cloudflare Named Tunnel (Windows)

This folder is for production-like setup without `trycloudflare.com`.

## Quick start (recommended)
1) Start server locally:
```powershell
cd server
python -m uvicorn asgi_realtime:app --host 127.0.0.1 --port 8000
```

2) Create named tunnel + config + DNS:
```powershell
cd server\deploy\cloudflare
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\named_tunnel_setup.ps1 -TunnelName "mapv12" -Domain "madcommandcentre.org"
```

3) Run tunnel:
```powershell
cloudflared tunnel run mapv12
```

4) Set `.env` for bootstrap links (so Telegram sends correct HTTPS URL):
```env
BOOTSTRAP_PREFERRED_BASE_URL=https://madcommandcentre.org
REALTIME_ALLOWED_ORIGINS=https://madcommandcentre.org
REALTIME_DISABLE_SAMEPORT=0
SESSION_COOKIE_SECURE=1
```

5) Optional: protect admin via Cloudflare Access:
- see `CLOUDFLARE_ACCESS_SETUP.md`

## Files
- `named_tunnel_setup.ps1` - automates tunnel creation and writes config.yml
- `config.yml.template` - manual template if you prefer
- `CLOUDFLARE_ACCESS_SETUP.md` - Access policy guide
