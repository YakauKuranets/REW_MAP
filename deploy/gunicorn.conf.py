"""Пример конфигурации gunicorn для Map v12 + бот.

Запуск:
    gunicorn -c deploy/gunicorn.conf.py wsgi:app
"""

import multiprocessing

bind = "0.0.0.0:8000"

# Количество воркеров: 2-4 на ядро, можно подобрать под сервер
workers = multiprocessing.cpu_count() * 2 + 1

# Потоки внутри воркера (подходит для I/O-нагруженных приложений)
worker_class = "gthread"
threads = 4

timeout = 30

# Логи gunicorn — в stdout/stderr (подходит для docker/journalctl)
accesslog = "-"
errorlog = "-"
loglevel = "info"
