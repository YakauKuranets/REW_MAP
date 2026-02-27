"""Open multiple WebSocket clients and keep them alive.

Usage:
  python ws_clients.py --url "wss://madcommandcentre.org/ws?token=..." --n 20 --minutes 60

Notes:
- Requires: pip install websockets
- URL must include token (get it from /api/realtime/token when logged in as admin).
"""

from __future__ import annotations

import argparse
import asyncio
import time


async def _client(idx: int, url: str, duration_s: int, ping_s: int = 25) -> None:
    import websockets  # type: ignore

    started = time.time()
    tries = 0
    while time.time() - started < duration_s:
        tries += 1
        try:
            async with websockets.connect(url, ping_interval=None) as ws:
                # manual ping (text), compatible with server's receive_text loop
                last_ping = 0.0
                while time.time() - started < duration_s:
                    now = time.time()
                    if now - last_ping >= ping_s:
                        try:
                            await ws.send("ping")
                        except Exception:
                            break
                        last_ping = now
                    try:
                        # wait for any message (or timeout)
                        await asyncio.wait_for(ws.recv(), timeout=ping_s)
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break
        except Exception:
            await asyncio.sleep(min(2 + tries * 0.25, 10))


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--minutes", type=int, default=10)
    args = p.parse_args()

    duration_s = max(1, int(args.minutes) * 60)
    tasks = [asyncio.create_task(_client(i + 1, args.url, duration_s)) for i in range(max(1, args.n))]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
