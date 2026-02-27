#!/usr/bin/env python
"""
Perf sanity check (quick load smoke).

Usage:
  # against already running server
  python tools/perf_sanity.py --base http://127.0.0.1:8000 --runs 200 --concurrency 20

  # optionally: start local ASGI server automatically (requires uvicorn)
  python tools/perf_sanity.py --spawn --runs 200 --concurrency 20

Notes:
  - This is NOT a full benchmark. It's a quick regression/sanity check for:
      /health
      /api/chat/conversations
      /api/chat/<user_id> (tail)
      /api/tracker/admin/devices
      /api/realtime/token (POST, CSRF)
"""

from __future__ import annotations

import argparse
import os
import socket
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

import requests


@dataclass
class Result:
    ok: int
    fail: int
    durations: list[float]


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_http(base_url: str, timeout_sec: float = 10.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = requests.get(base_url + "/health", timeout=0.8)
            if r.status_code in (200, 404):
                return
        except Exception:
            pass
        time.sleep(0.15)
    raise RuntimeError("Server did not start (timeout)")


def extract_csrf_cookie(s: requests.Session) -> str | None:
    for c in s.cookies:
        if c.name == "csrf_token":
            return c.value
    return None


def login_admin(base_url: str) -> tuple[requests.Session, dict]:
    s = requests.Session()
    r = s.post(base_url + "/login", json={"username": "admin", "password": "admin"}, timeout=2.0)
    if r.status_code not in (200, 204):
        raise RuntimeError(f"Login failed: {r.status_code}: {r.text}")
    csrf = extract_csrf_cookie(s)
    headers = {}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return s, headers


def seed_chat(s: requests.Session, base_url: str, headers: dict, user_id: str) -> None:
    s.post(base_url + f"/api/chat/{user_id}", json={"text": "perf-seed"}, headers=headers, timeout=2.0)


def run_load(fn: Callable[[], int], runs: int, concurrency: int) -> Result:
    ok = 0
    fail = 0
    durations: list[float] = []
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(fn) for _ in range(runs)]
        for fut in as_completed(futs):
            try:
                dur = fut.result()
                durations.append(dur / 1000.0)
                ok += 1
            except Exception:
                fail += 1
    return Result(ok=ok, fail=fail, durations=durations)


def report(name: str, res: Result) -> None:
    if not res.durations:
        print(f"{name}: no data")
        return
    p50 = statistics.median(res.durations)
    p95 = sorted(res.durations)[int(len(res.durations) * 0.95) - 1]
    mx = max(res.durations)
    print(f"{name}: ok={res.ok} fail={res.fail} p50={p50:.3f}s p95={p95:.3f}s max={mx:.3f}s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="", help="Base URL, e.g. http://127.0.0.1:8000")
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--spawn", action="store_true", help="Spawn local ASGI server via uvicorn")
    args = ap.parse_args()

    p = None
    base = args.base.strip()

    if args.spawn:
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["TESTING"] = "1"
        env["PORT"] = str(port)
        p = subprocess.Popen(
            ["python", "-m", "uvicorn", "asgi_realtime:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    if not base:
        raise SystemExit("Provide --base or use --spawn")

    try:
        wait_http(base)
        s, headers = login_admin(base)
        user_id = "perf_user_1"
        seed_chat(s, base, headers, user_id)

        # cookies (thread-safe dict)
        cookies = s.cookies.get_dict()

        def mk_get(path: str):
            def _call() -> int:
                t0 = time.perf_counter()
                r = requests.get(base + path, cookies=cookies, timeout=2.0)
                if r.status_code != 200:
                    raise RuntimeError(r.status_code)
                return int((time.perf_counter() - t0) * 1000)
            return _call

        def mk_post(path: str):
            def _call() -> int:
                t0 = time.perf_counter()
                r = requests.post(base + path, cookies=cookies, headers=headers, timeout=2.0)
                if r.status_code != 200:
                    raise RuntimeError(r.status_code)
                return int((time.perf_counter() - t0) * 1000)
            return _call

        res_health = run_load(mk_get("/health"), args.runs, args.concurrency)
        res_convs = run_load(mk_get("/api/chat/conversations?limit=50&offset=0"), args.runs, args.concurrency)
        res_hist = run_load(mk_get(f"/api/chat/{user_id}?limit=50&tail=1"), args.runs, args.concurrency)
        res_devs = run_load(mk_get("/api/tracker/admin/devices?limit=200&offset=0"), args.runs, args.concurrency)
        res_token = run_load(mk_post("/api/realtime/token"), max(50, args.runs // 4), max(5, args.concurrency // 4))

        print("\n=== Perf sanity ===")
        report("GET /health", res_health)
        report("GET /api/chat/conversations", res_convs)
        report("GET /api/chat/<uid> (tail)", res_hist)
        report("GET /api/tracker/admin/devices", res_devs)
        report("POST /api/realtime/token", res_token)

    finally:
        if p is not None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


if __name__ == "__main__":
    main()
