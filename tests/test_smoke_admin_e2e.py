import os
import re
import socket
import subprocess
import time

import pytest
import requests


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_http(base_url: str, timeout_sec: float = 8.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = requests.get(base_url + "/health", timeout=0.8)
            if r.status_code in (200, 404):
                return
        except Exception:
            pass
        time.sleep(0.15)
    raise RuntimeError("ASGI server did not start")


def _extract_csrf_cookie(s: requests.Session) -> str | None:
    # ищем csrf_token в Set-Cookie
    for c in s.cookies:
        if c.name == "csrf_token":
            return c.value
    return None


def _login_admin(base_url: str) -> requests.Session:
    s = requests.Session()
    r = s.post(base_url + "/login", json={"username": "admin", "password": "admin"}, timeout=2.0)
    assert r.status_code in (200, 204), r.text
    return s


@pytest.mark.e2e
def test_admin_pages_smoke_e2e(tmp_path):
    port = _free_port()
    base = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    # isolate DB for e2e
    db_path = tmp_path / 'e2e.db'
    env['DATABASE_URI'] = f"sqlite:///{db_path}"
    env["TESTING"] = "1"
    env["PORT"] = str(port)

    p = subprocess.Popen(
        ["python", "-m", "uvicorn", "asgi_realtime:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        _wait_http(base)

        s = _login_admin(base)
        csrf = _extract_csrf_cookie(s)

        # проверяем несколько ключевых страниц админки
        for path in ("/admin/panel", "/admin/chat", "/admin/devices", "/admin/duty"):
            r = s.get(base + path, timeout=3.0)
            assert r.status_code == 200, f"{path}: {r.status_code}"

        # токен realtime должен выдаваться только админам
        headers = {}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        r = s.post(base + "/api/realtime/token", headers=headers, timeout=3.0)
        assert r.status_code == 200
        j = r.json()
        assert "token" in j and isinstance(j["token"], str) and len(j["token"]) > 10

    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()
