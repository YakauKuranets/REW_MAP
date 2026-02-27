# Runbook — Map v12 (prod)

## Архитектура контейнеров (docker compose)
- **web**: Flask/Gunicorn (HTTP API + страницы)
- **worker**: фоновые задачи (schedulers/очереди), слушает Redis Pub/Sub
- **db**: PostgreSQL
- **redis**: брокер Pub/Sub и rate-limit (если включён)
- **nginx**: reverse-proxy (статик + websocket)

См. `deploy/README_DEPLOY.md` и `docker-compose.prod.yml`.

## Быстрый запуск (prod)
1) Создать `.env` рядом с `docker-compose.prod.yml` (или экспортировать env):
   - `SECRET_KEY`
   - `DATABASE_URL` (Postgres)
   - `REDIS_URL`
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` (legacy) **или** создать AdminUser в БД
   - `BOT_API_KEY` (рекомендуется, чтобы защитить bot->server вызовы)
   - `SESSION_COOKIE_SECURE=1` (если HTTPS)
   - `ENABLE_METRICS=1` (опционально)

2) Запуск:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

3) Миграции:
   ```bash
   docker compose -f docker-compose.prod.yml exec web alembic upgrade head
   ```

## Health / Ready
- `GET /health` — проверка приложения и DB (лёгкий SELECT 1).
- `GET /ready` — DB + Redis (если `REDIS_URL` задан). При проблемах вернёт **503**.

## Метрики
- По умолчанию `GET /metrics` отдаёт Prometheus text format.
- Защита:
  - В приложении: `METRICS_ALLOW_PUBLIC=0` (по умолчанию) — только localhost.
  - Альтернатива: задать `METRICS_API_KEY` и скрапить метрики с заголовком `X-API-KEY: ...`.
  - В nginx: `location = /metrics` можно дополнительно ограничить по IP.

## Rate limiting
- `/login`: `RATE_LIMIT_LOGIN_PER_MINUTE` (по умолчанию 10/min на IP)
- чат endpoints: `RATE_LIMIT_CHAT_PER_MINUTE` (по умолчанию 120/min на IP)
- bot endpoints:
  - `/api/bot/markers`: `RATE_LIMIT_BOT_MARKERS_PER_MINUTE`
  - `/api/bot/marker/*`: `RATE_LIMIT_BOT_STATUS_PER_MINUTE`, `RATE_LIMIT_BOT_CANCEL_PER_MINUTE`
  - `/api/bot/my_requests`: `RATE_LIMIT_BOT_MYREQ_PER_MINUTE`
  - `/api/duty/bot/*`: `RATE_LIMIT_DUTY_*_PER_MINUTE` (см. `app/config.py`)
  - duty bot: `RATE_LIMIT_DUTY_*_PER_MINUTE` (см. `.env.example`)
- Если доступен Redis — лимиты учитываются в Redis, иначе in-memory.

## Типовые инциденты

### 1) 502/504 от nginx
- Проверить `web`:
  ```bash
  docker compose -f docker-compose.prod.yml logs -n 200 web
  ```
- Проверить, что `web:8000` слушает и gunicorn стартовал без ошибок.
- Проверить переменные окружения (`DATABASE_URL`, `SECRET_KEY`).

### 2) /ready показывает db=error
- Проверить Postgres:
  ```bash
  docker compose -f docker-compose.prod.yml logs -n 200 db
  ```
- Проверить `DATABASE_URL` и миграции `alembic upgrade head`.

### 3) /ready показывает redis=error
- Проверить Redis:
  ```bash
  docker compose -f docker-compose.prod.yml logs -n 200 redis
  ```
- Проверить `REDIS_URL` и доступность сети внутри compose.

### 4) Бот перестал отправлять/получать сообщения чата
- Если включён `BOT_API_KEY`, убедиться, что он одинаковый:
  - в `.env` сервера (`BOT_API_KEY=...`)
  - в `.env`/переменных бота (`BOT_API_KEY=...`)
- Проверить логи `bot` (если бот в отдельном процессе) и `web`.

## Бэкапы
- PostgreSQL: регулярный `pg_dump` (cron/backup job).
- Важное: хранить бэкапы вне хоста (S3/облако/другой сервер).

## Backup/Restore (Postgres)

В `docker-compose.prod.full.yml` сервис `db` монтирует:
- `./deploy` → `/scripts` (read-only)
- `./backups` → `/backups`

### Backup
```bash
docker compose -f docker-compose.prod.full.yml exec -T db bash -lc "/scripts/backup_postgres.sh"
```

### Restore
```bash
docker compose -f docker-compose.prod.full.yml exec -T db bash -lc "/scripts/restore_postgres.sh /backups/pgdump_YYYYmmdd_HHMMSS.dump"
```


## Admin audit

Запись в БД таблицу `admin_audit_log` (best-effort). Просмотр: только superadmin.

- `GET /api/audit?limit=200&offset=0`
- фильтры: `action=...`, `actor=...`


## Perf sanity (быстрая проверка нагрузки)
- Скрипт: `tools/perf_sanity.py`.
- Пример (сам поднимет ASGI uvicorn):
  ```bash
  python tools/perf_sanity.py --spawn --runs 200 --concurrency 20
  ```
- Пример (если сервер уже запущен):
  ```bash
  python tools/perf_sanity.py --base http://127.0.0.1:8000 --runs 200 --concurrency 20
  ```

## Pagination / limits
- `GET /api/chat/<user_id>`: поддерживает `limit`, `offset`, `tail=1` (последние N сообщений). По умолчанию отдаёт последние 500.
- `GET /api/tracker/admin/devices`: поддерживает `limit`/`offset` и отдаёт `total/has_more`.
