from __future__ import annotations

"""Retention scheduler (best-effort).

This module adds an optional periodic retention cleanup runner.

Goals:
  - No new dependencies (threading + time).
  - Safe by default: scheduler is disabled unless explicitly enabled.
  - Best-effort multi-worker safety: if REDIS_URL is configured, we try to
    acquire a Redis lock before performing cleanup.

Important:
  In real production, prefer running schedulers in a dedicated worker process
  (not inside the web app) to avoid duplicated runs with multiple web workers.
"""

import threading
import time
from typing import Optional

from compat_flask import Flask

from ..maintenance.retention import run_retention_cleanup, set_last_retention_status


_thread: Optional[threading.Thread] = None


def _try_acquire_redis_lock(app: Flask) -> bool:
    """Acquire a best-effort distributed lock via Redis.

    Returns True if we acquired the lock or if Redis is not configured.
    Returns False if Redis is configured and the lock is already held.
    """
    redis_url = (app.config.get("REDIS_URL") or "").strip()
    if not redis_url:
        return True

    try:
        import redis as _redis  # type: ignore

        key = (app.config.get("RETENTION_SCHEDULER_LOCK_KEY") or "mapv12:retention:lock").strip()
        ttl = int(app.config.get("RETENTION_SCHEDULER_LOCK_TTL_SEC") or 600)
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        ok = r.set(name=key, value=str(int(time.time())), nx=True, ex=ttl)
        return bool(ok)
    except Exception:
        # If Redis is broken/misconfigured, do not block the scheduler.
        app.logger.debug("Retention scheduler: Redis lock failed", exc_info=True)
        return True


def start_retention_scheduler(app: Flask) -> None:
    """Start periodic retention cleanup in a daemon thread (if enabled)."""
    global _thread

    if _thread is not None:
        return

    if not bool(app.config.get("RETENTION_SCHEDULER_ENABLED", False)):
        return

    every_min = int(app.config.get("RETENTION_SCHEDULER_EVERY_MINUTES") or 0)
    if every_min <= 0:
        app.logger.warning("Retention scheduler enabled, but interval is invalid: %s", every_min)
        return

    start_delay = int(app.config.get("RETENTION_SCHEDULER_START_DELAY_SEC") or 0)

    def _loop() -> None:
        if start_delay > 0:
            time.sleep(start_delay)
        interval_sec = max(60, every_min * 60)

        while True:
            try:
                with app.app_context():
                    if not _try_acquire_redis_lock(app):
                        # Another worker holds the lock.
                        set_last_retention_status({
                            "kind": "skipped",
                            "reason": "redis_lock_held",
                            "ts": int(time.time()),
                        })
                    else:
                        rep = run_retention_cleanup(dry_run=False)
                        set_last_retention_status({
                            "kind": "run",
                            "ts": int(time.time()),
                            "report": rep,
                        })
                        app.logger.info("Retention scheduled cleanup finished: %s", rep)
            except Exception as e:
                try:
                    with app.app_context():
                        set_last_retention_status({
                            "kind": "error",
                            "ts": int(time.time()),
                            "error": repr(e),
                        })
                except Exception:
                    pass
                app.logger.exception("Retention scheduled cleanup failed")

            time.sleep(interval_sec)

    _thread = threading.Thread(target=_loop, name="retention-scheduler", daemon=True)
    _thread.start()
    app.logger.info(
        "Retention scheduler started: every=%s min, start_delay=%s sec", every_min, start_delay
    )
