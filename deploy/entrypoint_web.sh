#!/bin/sh
set -e

# Унифицированный entrypoint для прод‑контура.
#
# Поддерживаем два режима:
#  1) ASGI (рекомендуется): uvicorn + asgi_realtime:app (HTTP + WebSocket на одном порту)
#  2) WSGI (legacy): gunicorn + wsgi:app
#
# Управляется переменными:
#  - WEB_MODE=asgi|wsgi  (по умолчанию asgi)
#  - PORT=8000
#  - RUN_MIGRATIONS=1    (по умолчанию 1)

WEB_MODE="${WEB_MODE:-asgi}"
PORT="${PORT:-8000}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-1}"

if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "[entrypoint] Running migrations (alembic upgrade head) ..."
  # Важно: если БД не готова (например, Postgres только поднимается),
  # лучше упасть и дать Docker перезапустить контейнер.
  alembic upgrade head
fi

if [ "$WEB_MODE" = "wsgi" ]; then
  echo "[entrypoint] Starting WSGI (gunicorn) on :$PORT"
  exec gunicorn -c deploy/gunicorn.conf.py wsgi:app
fi

echo "[entrypoint] Starting ASGI (uvicorn asgi_realtime:app) on :$PORT"
exec uvicorn asgi_realtime:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips "*"
