"""tracker_stress.py

Небольшой DEV-стресс-тест для DutyTracker API.

Идея:
- логинимся админом
- генерируем N pairing-кодов (/api/tracker/admin/pair-code)
- для каждого кода делаем публичный pair (/api/tracker/pair) и получаем device_token
- запускаем N потоков, каждый шлёт:
    - /api/tracker/start
    - /api/tracker/health (heartbeat)
    - /api/tracker/points (пачки точек)
    - /api/tracker/stop

Требования: requests (есть в requirements.txt)

Пример:
  python tools/tracker_stress.py --base http://127.0.0.1:8000 --username admin --password ... --devices 10 --minutes 5
"""

from __future__ import annotations

import json
from datetime import datetime
import argparse
import os
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

import requests


@dataclass
class DeviceConfig:
    device_id: str
    device_token: str
    seed_lat: float
    seed_lon: float


class Stats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.ok = 0
        self.err = 0
        self.last_err: Optional[str] = None

    def inc_ok(self) -> None:
        with self.lock:
            self.ok += 1

    def inc_err(self, msg: str) -> None:
        with self.lock:
            self.err += 1
            self.last_err = msg


def _extract_csrf(html: str) -> Optional[str]:
    # <meta name="csrf-token" content="...">
    m = re.search(r'name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html, re.I)
    return m.group(1) if m else None



def _parse_int_set(raw: str) -> list[str]:
    ids = []
    for x in (raw or '').split(','):
        s = (x or '').strip()
        if s:
            ids.append(s)
    return ids


def _send_tg(bot_token: str, chat_id: str, text: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = requests.post(url, data={"chat_id": str(chat_id), "text": text, "disable_web_page_preview": True}, timeout=12)
        if not r.ok:
            return False
        j = r.json()
        return bool(j.get("ok"))
    except Exception:
        return False

def admin_login(base: str, username: str, password: str) -> tuple[requests.Session, str]:
    s = requests.Session()

    r = s.post(f"{base}/login", json={"username": username, "password": password}, timeout=15)
    r.raise_for_status()

    # Вытаскиваем CSRF из HTML админки (в сессии он уже есть, но нужен в заголовке)
    r2 = s.get(f"{base}/admin/panel", timeout=15)
    r2.raise_for_status()
    token = _extract_csrf(r2.text)
    if not token:
        raise RuntimeError("CSRF token not found in /admin/panel (meta csrf-token)")

    return s, token


def admin_pair_device(base: str, admin_sess: requests.Session, csrf: str, label: str) -> DeviceConfig:
    headers = {"X-CSRF-Token": csrf}

    r = admin_sess.post(f"{base}/api/tracker/admin/pair-code", json={"label": label}, headers=headers, timeout=15)
    r.raise_for_status()
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"pair-code failed: {j}")
    code = j.get("code")
    if not code:
        raise RuntimeError(f"pair-code: missing code: {j}")

    r2 = requests.post(f"{base}/api/tracker/pair", json={"code": str(code)}, timeout=15)
    r2.raise_for_status()
    j2 = r2.json()
    if not j2.get("ok"):
        raise RuntimeError(f"pair failed: {j2}")

    device_token = j2.get("device_token")
    device_id = j2.get("device_id")
    if not device_token or not device_id:
        raise RuntimeError(f"pair: missing token/device_id: {j2}")

    # небольшое случайное смещение, чтобы точки не совпадали у всех
    seed_lat = 53.90 + random.uniform(-0.02, 0.02)
    seed_lon = 27.56 + random.uniform(-0.02, 0.02)

    return DeviceConfig(device_id=device_id, device_token=device_token, seed_lat=seed_lat, seed_lon=seed_lon)


def run_device(base: str, cfg: DeviceConfig, minutes: float, points_every: float, health_every: float, batch: int, stats: Stats) -> None:
    sess = requests.Session()
    h = {"X-DEVICE-TOKEN": cfg.device_token}

    lat = cfg.seed_lat
    lon = cfg.seed_lon

    session_id: Optional[int] = None
    try:
        r = sess.post(f"{base}/api/tracker/start", json={"lat": lat, "lon": lon}, headers=h, timeout=15)
        r.raise_for_status()
        j = r.json()
        if not j.get("ok"):
            raise RuntimeError(f"start failed: {j}")
        session_id = j.get("session_id")
        if not session_id:
            raise RuntimeError(f"start: missing session_id: {j}")

        t0 = time.time()
        t_end = t0 + minutes * 60.0
        last_points = 0.0
        last_health = 0.0

        while time.time() < t_end:
            now = time.time()

            # здоровье
            if now - last_health >= health_every:
                payload = {
                    "battery_pct": max(5, 100 - int((now - t0) / 6)),
                    "is_charging": False,
                    "net": "wifi",
                    "gps": "ok",
                    "accuracy_m": max(5.0, random.uniform(5.0, 25.0)),
                    "queue_size": 0,
                    "tracking_on": True,
                    "last_error": None,
                    "app_version": "stress",
                    "device_model": "stressbot",
                    "os_version": "14",
                }
                rr = sess.post(f"{base}/api/tracker/health", json=payload, headers=h, timeout=15)
                rr.raise_for_status()
                stats.inc_ok()
                last_health = now

            # точки
            if now - last_points >= points_every:
                pts: List[Dict[str, Any]] = []
                # симулируем небольшое движение
                lat += random.uniform(-0.00008, 0.00008)
                lon += random.uniform(-0.00012, 0.00012)

                base_ts = time.time()
                for k in range(batch):
                    pts.append({
                        "lat": lat + random.uniform(-0.00001, 0.00001),
                        "lon": lon + random.uniform(-0.00001, 0.00001),
                        "ts": base_ts - (batch - k) * 0.2,
                        "acc": max(5.0, random.uniform(5.0, 30.0)),
                        "speed": random.uniform(0.0, 3.0),
                        "bearing": random.uniform(0.0, 360.0),
                    })

                rr = sess.post(
                    f"{base}/api/tracker/points",
                    json={"session_id": session_id, "points": pts},
                    headers=h,
                    timeout=15,
                )
                rr.raise_for_status()
                stats.inc_ok()
                last_points = now

            time.sleep(0.20)

    except Exception as e:
        stats.inc_err(f"{cfg.device_id}: {e}")

    finally:
        if session_id is not None:
            try:
                sess.post(f"{base}/api/tracker/stop", json={"session_id": session_id}, headers=h, timeout=10)
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("MAP_API_URL") or "http://127.0.0.1:8000", help="Base URL (например http://127.0.0.1:8000)")
    ap.add_argument("--username", default=os.environ.get("ADMIN_USERNAME") or "", help="Admin username")
    ap.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD") or "", help="Admin password")
    ap.add_argument("--devices", type=int, default=5, help="Сколько устройств симулировать")
    ap.add_argument("--minutes", type=float, default=2.0, help="Сколько минут гонять")
    ap.add_argument("--points-every", type=float, default=2.0, help="Интервал отправки точек, сек")
    ap.add_argument("--health-every", type=float, default=10.0, help="Интервал heartbeat, сек")
    ap.add_argument("--batch", type=int, default=5, help="Сколько точек в пачке")
    ap.add_argument("--report", default='', help='Путь для JSON-отчёта (например reports/stress.json)')
    ap.add_argument("--metrics-every", type=float, default=0.0, help="Если >0 — опрашивать /api/tracker/admin/metrics каждые N сек и сохранить series в report")
    ap.add_argument("--tg-chat-id", default='', help='Куда отправить итог в Telegram (chat_id). Если пусто — возьмём ADMIN_TELEGRAM_IDS из env')


    args = ap.parse_args()

    base = args.base.rstrip("/")
    if not args.username or not args.password:
        print("ERROR: укажи --username/--password (или env ADMIN_USERNAME/ADMIN_PASSWORD)")
        return 2

    print(f"[stress] base={base} devices={args.devices} minutes={args.minutes} points_every={args.points_every}s health_every={args.health_every}s batch={args.batch}")

    admin_sess, csrf = admin_login(base, args.username, args.password)
    print("[stress] admin login ok")

    devs: List[DeviceConfig] = []
    for i in range(args.devices):
        cfg = admin_pair_device(base, admin_sess, csrf, label=f"stress-{i+1}")
        devs.append(cfg)
        print(f"[stress] paired {cfg.device_id}")

    stats = Stats()
    threads: List[threading.Thread] = []
    for cfg in devs:
        t = threading.Thread(
            target=run_device,
            args=(base, cfg, args.minutes, args.points_every, args.health_every, args.batch, stats),
            daemon=True,
        )
        threads.append(t)
        t.start()

    # опрос метрик в фоне (опционально)
    metrics_series = []
    stop_evt = threading.Event()
    thm = None
    if args.metrics_every and args.metrics_every > 0:
        def _metrics_poller():
            while not stop_evt.is_set():
                try:
                    r = admin_sess.get(f"{base}/api/tracker/admin/metrics", timeout=10)
                    item = {"ts": datetime.utcnow().isoformat(), "status": int(getattr(r, "status_code", 0))}
                    if getattr(r, "ok", False):
                        try:
                            item["data"] = r.json()
                        except Exception:
                            item["data"] = None
                    else:
                        item["data"] = None
                    metrics_series.append(item)
                except Exception as e:
                    metrics_series.append({"ts": datetime.utcnow().isoformat(), "status": 0, "error": str(e)})
                stop_evt.wait(float(args.metrics_every))
        thm = threading.Thread(target=_metrics_poller, daemon=True)
        thm.start()

    for t in threads:
        t.join()

    if thm is not None:
        stop_evt.set()
        try:
            thm.join(timeout=2.0)
        except Exception:
            pass

    print(f"[stress] done: ok={stats.ok} err={stats.err}")
    if stats.last_err:
        print(f"[stress] last_err: {stats.last_err}")

    # быстро проверим метрики
    metrics_json = None
    try:
        r = admin_sess.get(f"{base}/api/tracker/admin/metrics", timeout=10)
        print(f"[stress] metrics status={r.status_code}")
        if r.ok:
            metrics_json = r.json()
            m = (metrics_json.get('metrics') or {}) if isinstance(metrics_json, dict) else {}
            print(f"[stress] metrics: online={m.get('online_devices')} active_alerts={m.get('active_alerts')} points_last_5m={m.get('points_last_5m')}")
    except Exception:
        pass

    # JSON отчёт
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "base": base,
        "devices": args.devices,
        "minutes": args.minutes,
        "points_every_sec": args.points_every,
        "health_every_sec": args.health_every,
        "batch": args.batch,
        "stats": {"ok": stats.ok, "err": stats.err, "last_err": stats.last_err},
        "metrics": metrics_json,
        "metrics_series": metrics_series,
    }

    if args.report:
        try:
            os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"[stress] report saved: {args.report}")
        except Exception as e:
            print(f"[stress] report save failed: {e}")

    # Telegram итог (опционально)
    bot_token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if bot_token:
        targets = []
        if args.tg_chat_id:
            targets = [args.tg_chat_id]
        else:
            targets = _parse_int_set(os.environ.get("ADMIN_TELEGRAM_IDS") or "")
        if targets:
            try:
                m = (metrics_json.get("metrics") or {}) if isinstance(metrics_json, dict) else {}
                msg = (
                    f"[stress] done devices={args.devices} minutes={args.minutes} ok={stats.ok} err={stats.err}\n"
                    f"metrics: online={m.get('online_devices')} alerts={m.get('active_alerts')} points5m={m.get('points_last_5m')}"
                )
                for chat_id in targets:
                    _send_tg(bot_token, str(chat_id), msg)
            except Exception:
                pass


    return 0


if __name__ == "__main__":
    raise SystemExit(main())