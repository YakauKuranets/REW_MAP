"""Background worker for schedulers (Duty + Tracker alerting).

Запускается отдельным процессом/контейнером в прод‑контуре.

Зачем:
  - избежать дублей фоновых потоков при нескольких web‑воркерах/репликах
  - держать фоновые задачи и web отдельно (проще мониторить/рестартить)
  - опционально использовать Redis‑lock, чтобы гарантировать единственный active worker

Запуск (пример):
  python worker.py

Переменные окружения:
  APP_ENV=production|development|testing
  ENABLE_INTERNAL_SCHEDULERS=0|1   (для web обычно 0; для worker не обязательно)
  REDIS_URL=redis://redis:6379/0    (опционально, но рекомендуется в проде)
  SCHEDULER_LOCK_KEY=mapv12:schedulers:lock
  SCHEDULER_LOCK_TTL_SEC=60

Интервалы:
  DUTY_SCHEDULER_INTERVAL_SEC=30
  TRACKER_ALERTS_INTERVAL_SEC=10
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Optional

from app import create_app
from app.config import ProductionConfig, DevelopmentConfig, TestingConfig

# Optional redis lock
try:
    from redis import Redis
except Exception:  # pragma: no cover
    Redis = None  # type: ignore[assignment]


def get_config_class():
    cfg_name = (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "production").lower()
    if cfg_name in {"dev", "development"}:
        return DevelopmentConfig
    if cfg_name in {"test", "testing"}:
        return TestingConfig
    return ProductionConfig


def _redis_client_from_env() -> Optional["Redis"]:
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url or Redis is None:
        return None
    try:
        return Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _acquire_lock(r: "Redis", key: str, token: str, ttl: int) -> bool:
    # SET key token NX EX ttl
    try:
        return bool(r.set(key, token, nx=True, ex=ttl))
    except Exception:
        return False


def _renew_lock(r: "Redis", key: str, token: str, ttl: int) -> bool:
    # продлеваем только если значение совпадает (простая защита)
    try:
        current = r.get(key)
        if current != token:
            return False
        return bool(r.set(key, token, xx=True, ex=ttl))
    except Exception:
        return False


def main() -> int:
    # В worker НЕ запускаем встроенные фоновые потоки create_app (мы управляем циклом сами).
    os.environ["ENABLE_INTERNAL_SCHEDULERS"] = "0"

    app = create_app(get_config_class())

    lock_key = os.getenv("SCHEDULER_LOCK_KEY", app.config.get("SCHEDULER_LOCK_KEY", "mapv12:schedulers:lock"))
    lock_ttl = int(os.getenv("SCHEDULER_LOCK_TTL_SEC", app.config.get("SCHEDULER_LOCK_TTL_SEC", 60)))
    lock_token = f"{os.getenv('HOSTNAME', 'worker')}:{uuid.uuid4().hex}"

    duty_interval = int(os.getenv("DUTY_SCHEDULER_INTERVAL_SEC", "30"))
    tracker_interval = int(os.getenv("TRACKER_ALERTS_INTERVAL_SEC", "10"))

    # Импортируем тики
    from app.duty.routes import duty_scheduler_tick
    from app.tracker.alerting import tracker_alerts_tick, tracker_retention_tick

    r = _redis_client_from_env()

    if r:
        # Ждём lock
        while True:
            if _acquire_lock(r, lock_key, lock_token, lock_ttl):
                app.logger.info(f"[worker] scheduler lock acquired: {lock_key}")
                break
            app.logger.warning(f"[worker] scheduler lock busy, retry in 5s: {lock_key}")
            time.sleep(5)
    else:
        app.logger.warning("[worker] REDIS_URL not set or redis unavailable: running WITHOUT distributed lock")

    next_duty = 0.0
    next_tracker = 0.0
    last_retention = 0.0
    next_renew = time.time() + max(5, lock_ttl // 2)

    while True:
        now = time.time()

        # renew lock
        if r and now >= next_renew:
            ok = _renew_lock(r, lock_key, lock_token, lock_ttl)
            if not ok:
                app.logger.error("[worker] scheduler lock lost; exiting to avoid duplicates")
                return 2
            next_renew = now + max(5, lock_ttl // 2)

        # ticks
        try:
            with app.app_context():
                if now >= next_duty:
                    duty_scheduler_tick()
                    next_duty = now + max(5, duty_interval)

                if now >= next_tracker:
                    tracker_alerts_tick(app)
                    next_tracker = now + max(3, tracker_interval)

                # retention 1 раз в сутки
                if now - last_retention >= 24 * 3600:
                    tracker_retention_tick(app)
                    last_retention = now

        except Exception:
            app.logger.exception("[worker] scheduler tick failed")

        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
