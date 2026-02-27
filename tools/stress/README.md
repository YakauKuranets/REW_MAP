# Stress / long-run checks

Goal: run the system for 1–2 hours and watch that:
- WebSocket stays connected (no silent drop)
- API responds
- Dashboard keeps updating

## 1) Quick smoke (PowerShell)
```powershell
# replace with your public HTTPS (Named Tunnel)
$BASE = "https://madcommandcentre.org"

Invoke-WebRequest "$BASE/healthz" -UseBasicParsing
Invoke-WebRequest "$BASE/readyz" -UseBasicParsing
```

## 2) Realtime stats (admin)
If you are logged in to /admin in the same browser, you can check WS clients count:

- `GET /api/realtime/stats` (requires admin session)

## 3) Load WS clients (Python)
This opens N WS clients and keeps them alive.

Install dependency:
```bash
pip install websockets
```

Run:
```bash
python ws_clients.py --url "wss://madcommandcentre.org/ws?token=..." --n 20 --minutes 60
```
