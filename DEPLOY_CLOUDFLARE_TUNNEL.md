# Публикация локального сервера в Интернет (HTTPS) без хостинга

> Для Stage40+ рекомендуется использовать готовые скрипты:
> `server/deploy/cloudflare/README.md` (Named Tunnel + DNS + config.yml).

Цель: чтобы Command Center и bootstrap для Android работали через **HTTPS** из интернета,
хотя сервер запущен локально на ПК (без проброса портов / без белого IP).

## Архитектура (что происходит)
Интернет (HTTPS) → Cloudflare Tunnel → (локально) **ASGI app** (Uvicorn) :8000

В Stage39 используется единый ASGI (HTTP + WebSocket на `/ws`) из файла `asgi_realtime.py`, поэтому **Caddy не обязателен**.

> Legacy (если вы всё ещё запускаете старую схему `run.py` + отдельный WS):
> Интернет (HTTPS) → Cloudflare Tunnel → Caddy :8080 → Flask :5000 + WS :8765

## Вариант A (быстро протестировать): Quick Tunnel (TryCloudflare)
Плюсы: 1 команда, не нужен домен, сразу HTTPS. Минус: URL меняется при каждом запуске.

### Шаги (актуально для Stage39)
1) Запусти ASGI-сервер (HTTP + WS) на 8000:
   - `python -m uvicorn asgi_realtime:app --host 0.0.0.0 --port 8000`
   - Проверка: открой `http://localhost:8000/`

2) Запусти Quick Tunnel:
   - Скачай `cloudflared` и добавь в PATH.
   - `cloudflared tunnel --url http://localhost:8000`
   - В консоли появится URL вида `https://xxxx.trycloudflare.com`

3) Открой Command Center уже по `https://xxxx.trycloudflare.com`
   - Тогда bootstrap-ссылки формируются с правильным https-доменом.

## Вариант B (на постоянку): Cloudflare Tunnel + домен
Плюсы: URL всегда один и тот же. Минус: нужен домен, добавленный в Cloudflare.

### Шаги (схема)
1) В Cloudflare Zero Trust создай Tunnel (тип cloudflared) и установи cloudflared на ПК.
2) В настройках Tunnel добавь Public Hostname:
   - hostname: `map.<твой_домен>`
   - service: `http://localhost:8000`
3) Запусти `cloudflared tunnel run <tunnel-name>` (или как сервис).
4) Открывай Command Center по `https://map.<твой_домен>`.

## Безопасность
Если ты публикуешь сервис в интернет:
- обязательно выставь сложные пароли/ключи (BOT_API_KEY, admin пароль)
- ограничь /admin по allowlist IP или BasicAuth (если надо)
- не логируй токены/ключи в публичные логи


## Stage18.3 — Named Tunnel (постоянный домен)

Quick Tunnel (`cloudflared tunnel --url ...`) удобен для DEV, но URL каждый раз новый.
Для «боевого» домена лучше сделать Named Tunnel и привязать его к своему домену.

### 1) Создать туннель
1. Установите `cloudflared` и авторизуйтесь:
   - `cloudflared tunnel login`
2. Создайте туннель:
   - `cloudflared tunnel create mapv12`

Вы получите `TUNNEL_ID` и файл `TUNNEL_ID.json` (credentials).

### 2) Привязать DNS
Пример для домена `cc.example.com`:
- `cloudflared tunnel route dns mapv12 cc.example.com`

### 3) Конфиг `config.yml`
Создайте `config.yml` рядом с `cloudflared`:
```yml
tunnel: mapv12
credentials-file: /path/to/TUNNEL_ID.json

ingress:
  - hostname: cc.example.com
    service: http://localhost:8000
  - service: http_status:404
```

Запуск:
- `cloudflared tunnel run mapv12`

### 4) В .env укажите постоянный BASE_URL
- `BOOTSTRAP_PREFERRED_BASE_URL=https://cc.example.com`

## Cloudflare Access (ограничение админки)

Минимальная идея: закрыть `/admin/*` политикой Access, а публичные API оставить по необходимости.

1. В Cloudflare Zero Trust → Access → Applications создайте приложение:
   - Self-hosted → Domain: `cc.example.com`
   - Path: `/admin/*`
2. Создайте Policy (Allow) только для нужных e-mail / групп.
3. Проверьте, что:
   - `/admin/*` требует вход
   - публичные эндпоинты (например `/healthz`, `/readyz`) доступны по настройке
