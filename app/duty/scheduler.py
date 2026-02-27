"""Фоновый таймер для Duty (обеды, проверки)."""

from __future__ import annotations

import os
import time
from threading import Thread
from typing import Optional

_thread: Optional[Thread] = None


def start_duty_scheduler(app) -> None:
    """Запустить фоновый поток (если не запущен).

    Чтобы избежать двойного запуска при debug-reload, используем:
    - WERKZEUG_RUN_MAIN == 'true' (рабочий процесс)
    - либо debug=False
    """
    global _thread
    if os.getenv('DISABLE_DUTY_SCHEDULER') == '1':
        return

    # Flask debug reloader запускает два процесса: guard.
    if app.debug and os.getenv('WERKZEUG_RUN_MAIN') != 'true':
        return

    if _thread and _thread.is_alive():
        return

    def _loop():
        with app.app_context():
            from .routes import duty_scheduler_tick  # локальный импорт
            while True:
                try:
                    duty_scheduler_tick()
                except Exception:
                    app.logger.exception('duty_scheduler_tick failed')
                time.sleep(int(os.getenv('DUTY_SCHEDULER_INTERVAL_SEC', '30')))

    _thread = Thread(target=_loop, daemon=True, name='duty-scheduler')
    _thread.start()
