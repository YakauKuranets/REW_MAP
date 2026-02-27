# Handoff (копируй целиком в новый чат)

## Последний контрольный архив
- **Stage41.20**: RMB‑меню карты → «Добавить инцидент здесь»; на главной карте добавлены модалка/кнопка создания инцидента; авто‑геокод по адресу при сохранении (если координаты не фиксировали вручную).

## Проект
**Map v12 / Command Center / DutyTracker / Telegram Bot**  
Цель: единая система для управления нарядами и live‑трекингом.

### Компоненты
- **Android (DutyTracker)**: собирает GPS + телеметрию (battery / сеть / GPS / очередь), шлёт точки в API/WS.
- **Server (Command Center + API + WS)**: хранит состояния, отдаёт UI, real‑time через WebSocket.
- **Telegram Bot**: доступы/роли/заявки, bootstrap‑привязка трекера, админские команды.

### Типовой поток
1) Пользователь в TG запрашивает доступ / подключение трекера.  
2) Админ подтверждает в `/admin/service`.  
3) Сервер автоматически отправляет в TG: **публичный HTTPS URL** + **pair code** + кнопку.  
4) Приложение привязывается → начинает live‑трекинг.  
5) Command Center показывает метку, accuracy‑круг, KPI, алёрты.

---

## Архитектура (упрощённо)

Telegram Bot ──► Server (Command Center + API + WS) ◄── Android DutyTracker  
       │                 ▲  
       └── bootstrap ────┘  

---

## Что уже сделано (краткий статус)

### Этапы 1–6: база и связка (100%)
- карта + WS real‑time, роли (RBAC), health/ready
- TG: роли, заявки, approve/deny, bootstrap
- Android: Foreground Service, очередь, offline, pairing
- HTTPS для локального сервера через Cloudflare Tunnel
- гостевая учётка удалена

### Этапы 7–13: UX и стабильность (100%)
- мобильный UI Command Center: аккуратная вёрстка, читаемая тёмная тема
- выбор входа (Админ карты / Командный центр), редиректы без 403
- авто‑сообщение после approve (BASE_URL + PAIR CODE + кнопка)
- счётчики pending, раздел “Служба” интегрирован

### Этапы 14–15: точность трекинга (~90–95%)
- фильтрация точек (stale/accuracy/jump reject)
- EMA‑сглаживание, детектор стоянки, режимы ECO/NORMAL/PRECISE/AUTO
- accuracy‑круг на карте
- dashboard получает `accuracy_m` из последней точки

### Этапы 16–17: Live Health / KPI / алёрты (100%)
- heartbeat ~15 сек (battery/net/gps/queue/accuracy/last_send)
- KPI обновляются live
- алёрты: net_offline, low_accuracy, tracking_off, app_error
- бейджи !/!!, страница `/admin/problems`

---

## Текущий фокус (что осталось сделать)

### Этап 18 — “боевой” UX + прод‑укрепление (осталось ~4–6%)
**18.1 Рекомендации пользователю (высокий эффект, быстро):**
- в UI “что сделать”: включить GPS, снять battery‑opt, проверить сеть, разрешения и т.п.

**18.2 История проблем/трека (средний объём):**
- история алёртов по устройству (24ч/7д), экспорт
- просмотр маршрута за период (polyline + GPX/CSV)

**18.3 Прод‑укрепление (требует домена/доступа):**
- Named Tunnel (постоянный домен, напр. `madcommandcentre.org`)
- ограничение админки (Cloudflare Access)
- стресс‑тест 1–2 часа

---

## Как запускать (dev + интернет)

### Сервер (единый порт)
```bash
python -m uvicorn asgi_realtime:app --host 0.0.0.0 --port 8000
```

### Cloudflare Quick Tunnel
```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000
```
Получить `https://xxxx.trycloudflare.com` и прописать в `.env`.

### .env (минимум)
```env
MAP_API_URL=http://127.0.0.1:8000
BOOTSTRAP_PREFERRED_BASE_URL=https://xxxx.trycloudflare.com
MOBILE_CONNECT_AUTO_SEND=1
TELEGRAM_BOT_TOKEN=...
```

---

## Последняя правка в этой версии (важное)
- **Command Center:** исправлено “пустое поле” слева/сверху от карты (из‑за глобального `style.css` для `#map`).
  Override добавлен в `static/css/admin_panel.css` под `body.admin #map.ap-map`.

- **Command Center:** исправлено "Показать" в карточке наряда: теперь всегда ставится явный **фокус‑маркер** на карте (отдельный слой `layers.focus`) + центрирование.
  Это помогает даже если маркеры смен по фильтрам/перерисовке временно не отрисованы.
  Файл: `static/js/admin_panel.js` (v32: функции `focusShiftOnMap` / `focusDetailOnMap`).


---

## Новое (Stage 34 / MAX-1)
- Android: добавлен сбор радио-отпечатков (Wi‑Fi + Cell), отправляется на сервер раз в ~60 сек.
- Server: добавлен endpoint `POST /api/tracker/fingerprints` ...
- Приватность: BSSID/SSID хэшируются на сервере.

Файлы:
- Android: `FingerprintCollector.kt`, `FingerprintStore.kt`, `UploadWorker.kt`, `AndroidManifest.xml`, `MainActivity.kt`
- Server: `app/models.py` (TrackerFingerprintSample), `app/tracker/routes.py` (api_fingerprints), `TRACKER_CONTRACT.md`


---

## Новое (Stage 35 / MAX-2) — indoor/low-GPS позиционирование (best-effort)
- Android: `purpose` теперь выставляется автоматически:
  - `train` если есть координата и `accuracy_m <= 60` (хороший GNSS)
  - `locate` если координаты нет или она ненадёжна
  (файл: `UploadWorker.kt`)
- Server: при `purpose=locate` пытается оценить позицию по похожести на **свои же** якорные отпечатки устройства (за 30 дней).
  Если совпадение хорошее — создаёт точку трека `kind='est'` и пушит в Command Center через WS (`source='wifi_est'`, `flags=['est']`).
  Дополнительно записывает `health.extra.pos_est` для диагностики.

Файл: `app/tracker/routes.py` (функции `_localize_by_fingerprint` / `_inject_estimated_point` + вызов из `api_fingerprints`).

---

## Новое (Stage 36) — История проблем/маршрут по периоду в Command Center + фиксы API

### Command Center
- В панели наряда добавлена “История проблем трекера” (tab **Журнал**):
  - фильтр 24ч/72ч/7д + active/all/closed
  - кастомный диапазон (from/to)
  - экспорт алёртов в CSV
  - ссылка на страницу устройства
  Файл: `static/js/admin_panel.js`

- В tab **Маршрут** добавлен режим “Маршрут по периоду (точки устройства)” с экспортом CSV/GPX.
  Это позволяет смотреть трек даже когда нет “сессии трекинга”, либо нужен произвольный период.
  Файл: `static/js/admin_panel.js`

### Server (API)
- `/api/tracker/admin/device/<id>/alerts`: исправлен баг `offset is not defined` (добавлен парсинг offset).
- `/api/tracker/admin/device/<id>/health_log`: добавлена корректная фильтрация по `from/to` (и fallback на `hours`).
  Файл: `app/tracker/routes.py`


---

## Новое (Stage 38 / 2026‑01‑05) — фикс “прочерков” + защита от вечного reject

### Android (DutyTracker)
- **Последняя отправка (tile/статус):** если `last_upload` пустой, показываем время **последнего health** (`last_health`).  
  Это убирает ситуацию “прочерк”, когда точки ещё не ушли, но связь/health уже работает.
  Файл: `MainActivity.kt` (`tvTileLast`, строка “Последняя отправка”).

- **Health payload:** `lastSendAtIso` теперь всегда непустой (fallback на `nowIso`), и безопасный код в error‑ветке.
  Файл: `UploadWorker.kt`, `ForegroundLocationService.kt`.

- **Фильтр точек:** добавлен режим “принудительно принять” (1 точка раз в ~30с), если трекер **45с+** не принял ни одной точки из‑за плохой точности, но accuracy не экстремальная (<=900м).
  Это нужно для зданий/плохого GNSS: лучше редкие точки с большим кругом, чем пустая карта.
  Файл: `TrackingQualityFilter.kt` (`force_acc …`).

### Server (Command Center)
- **/api/tracker/health:** если клиент не прислал `last_send_at`, сервер ставит `last_send_at = updated_at` (последний heartbeat).
- **WS event tracker_health:** добавлено поле `last_send_at`.
- **Admin Device Detail:** в карточку устройства добавлен KV “**Последняя отправка**” (берётся из `health.last_send_at`/`updated_at`).
  Файл: `static/js/admin_device_detail.js`.

### Ожидаемый эффект
- Уходит “—” в приложении/странице устройства при рабочем health.
- Даже при плохом GNSS трек не “зависает” в вечном reject → появляются точки/метка на карте.

---

## Текущая оценка готовности
- Система в целом: **~96–97%**
- Осталось до “приятного прод-уровня”: **~3–4%** (Этап 18: 18.1 + Named Tunnel + стресс‑тест)
