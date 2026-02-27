import asyncio
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests
import websockets


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _wait_http(url: str, timeout_sec: float = 10.0) -> None:
    start = time.time()
    last_err = None
    while time.time() - start < timeout_sec:
        try:
            r = requests.get(url, timeout=1)
            if r.status_code in (200, 204):
                return
        except Exception as e:
            last_err = e
        time.sleep(0.25)
    raise AssertionError(f"Server did not become ready: {url}. Last error: {last_err!r}")


def _extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    if not m:
        raise AssertionError("CSRF meta tag not found")
    return m.group(1)


@pytest.mark.e2e
def test_ws_receives_chat_message(tmp_path):
    """E2E: uvicorn(asgi_realtime) + login + WS connect + chat event."""

    proj_root = Path(__file__).resolve().parents[1]
    port = _free_port()
    base = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["DATABASE_URI"] = f"sqlite:///{tmp_path / 'e2e.db'}"
    env["APP_ENV"] = "development"
    # в e2e не поднимаем redis
    env.pop("REDIS_URL", None)

    p = subprocess.Popen(
        [
            "python",
            "-m",
            "uvicorn",
            "asgi_realtime:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(proj_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        _wait_http(f"{base}/health", timeout_sec=15)

        s = requests.Session()
        # login (CSRF exempt)
        r = s.post(f"{base}/login", json={"username": "admin", "password": "secret"}, timeout=5)
        assert r.status_code == 200

        # get csrf from admin page
        r = s.get(f"{base}/admin/panel", timeout=5)
        assert r.status_code == 200
        csrf = _extract_csrf(r.text)

        # token for WS
        r = s.get(f"{base}/api/realtime/token", timeout=5)
        assert r.status_code == 200
        tok = (r.json() or {}).get("token")
        assert tok

        ws_url = f"ws://127.0.0.1:{port}/ws?token={tok}"

        async def _run():
            async with websockets.connect(ws_url) as ws:
                # отправим сообщение (в отдельном thread, чтобы не блокировать loop)
                resp = await asyncio.to_thread(
                    s.post,
                    f"{base}/api/chat/u1",
                    json={"text": "hello", "sender": "admin"},
                    headers={"X-CSRF-Token": csrf},
                    timeout=5,
                )
                assert resp.status_code in (200, 201)

                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                msg = json.loads(raw)
                assert msg.get("event") == "chat_message"
                data = msg.get("data") or {}
                assert str(data.get("user_id")) == "u1"

        asyncio.run(_run())

    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()
