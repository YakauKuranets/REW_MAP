#!/bin/sh
set -e

# Worker для scheduler'ов (Duty/Tracker)
# Важно: миграции выполняем в web-контейнере, чтобы не было гонок.

echo "[worker] starting scheduler worker ..."
exec python worker.py
