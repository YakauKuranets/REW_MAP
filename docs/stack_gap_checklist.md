# Сверка по списку: что уже есть и чего пока нет

Дата сверки: 2026-02-27.

## 1) Ядро бэкенда (Python / API / Celery)

- ✅ **Модульная структура `app/*` и Celery присутствуют.**
- ⚠️ **FastAPI не найден как основной сервер**: проект сейчас на Flask (factory + WSGI), хотя в зависимостях есть Starlette/Uvicorn.
- ⚠️ **OpenTelemetry не найдено.**
- ✅/⚠️ **Метрики есть частично**: есть встроенные Prometheus-style метрики, но без отдельного Prometheus client/OTel-трейсинга.
- ⚠️ **JSON structured logging (`python-json-logger`) не найдено.**
- ⚠️ **Секреты в основном через env**, интеграций Vault/AWS Secrets Manager не найдено.
- ✅/⚠️ **Celery Beat есть**, но Flower и явная динамическая приоритизация очередей не обнаружены.

## 2) Шлюз телеметрии (Rust)

- ✅ **Есть отдельный Rust сервис `telemetry_node` на axum + Tokio.**
- ✅ **Rate limiting реализован** через `tower-governor`.
- ⚠️ **Backpressure по соединениям/семафорам явно не найден.**
- ⚠️ **Запись в Redis Streams (`XADD`) отсутствует**: сейчас publish в каналы Redis Pub/Sub.
- ⚠️ **Batch/pipeline для Redis не найдено.**
- ✅/⚠️ **Graceful shutdown частично**: логика завершения есть, но явные readiness/liveness endpoints в Rust-ноде не найдены.
- ✅ **Валидация входящих данных есть** (диапазоны lat/lon, finite-check).

## 3) Командный терминал (React + Electron)

- ✅ **React + Electron присутствуют** (`react_frontend`).
- ✅ **Deck.GL и Zustand присутствуют**.
- ⚠️ **`react-window` (виртуализация) не найдено.**
- ⚠️ **IndexedDB/Dexie офлайн-слой не найден.**
- ⚠️ **electron-builder/автообновления/подпись не найдены.**
- ⚠️ **Явные hardening-настройки Electron (contextBridge + отключение Node в renderer) нужно отдельно проверять по коду `public/electron.js`.**

## 4) Мобильные агенты (Android/Kotlin)

- ✅ **WorkManager уже используется** (включая Wi-Fi scan scheduler).
- ✅ **Mesh-логика присутствует** (есть `MeshNetworkManager`).
- ✅ **SQLCipher присутствует** (Room + `net.zetetic:android-database-sqlcipher`).
- ⚠️ **Reticulum не найден.**
- ⚠️ **Явные механизмы anti-tamper/self-destruct не обнаружены в явном виде этой сверкой.**
- ⚠️ **IMSI-сбор не подтверждён; GPS присутствует.**

## 5) Telegram-бот

- ✅ **Модуль `app/bot/*` есть, WebApp security middleware есть.**
- ⚠️ **MTProto proxy интеграция не найдена.**
- ⚠️ **TOTP/2FA для админ-команд не найдено.**
- ✅/⚠️ **Rate limiting есть best-effort в отдельных endpoint-ах,** но отдельного централизованного anti-bruteforce слоя не видно.
- ⚠️ **PDF-отчёты прямо в Telegram не подтверждены этой сверкой.**

## 6) Инфраструктура/деплой (DevSecOps)

- ✅ **Docker Compose есть (несколько профилей), Gunicorn и Alembic используются.**
- ✅ **Cloudflare Zero Trust/Tunnel отражены в документации.**
- ⚠️ **Kubernetes/Helm манифестов не найдено.**
- ⚠️ **CI/CD пайплайны (GitHub Actions/GitLab CI) не найдены.**
- ⚠️ **Trivy/ArgoCD не найдены.**
- ✅/⚠️ **Neo4j/Redis/Postgres используются,** но кластерные настройки (Causal Clustering, Redis Sentinel/Cluster, streaming replication) не найдены в текущих compose-файлах.
- ⚠️ **Tailscale/WireGuard интеграция не найдена.**
- ⚠️ **Prometheus+Alertmanager+Grafana как стек развёртывания не найдены (есть только внутренний metrics endpoint).**

## 7) Тестирование и инструменты

- ✅ **Папка `tests/` большая (51 файл).**
- ✅ **Есть stress-инструменты в `tools/stress`.**
- ⚠️ **Hypothesis не найден.**
- ⚠️ **testcontainers не найден.**
- ⚠️ **mutmut не найден.**

## 8) Общие рекомендации

- ✅ **README и проектная документация есть.**
- ⚠️ **PlantUML-схема архитектуры не найдена явным файлом.**
- ⚠️ **mypy в CI не найден (и CI-файлов не найдено).**
- ⚠️ **Pydantic как базовый слой моделей API не является текущим стандартом проекта (основа — Flask/SQLAlchemy).**
- ⚠️ **Dependabot/Safety/Bandit/SonarQube в пайплайнах не найдены.**

## Краткий итог

Проект уже покрывает значительную часть вашего списка по функционалу (модульность, Celery, Rust-нод, React/Electron, Android, Telegram-бот, Docker Compose, Alembic, большой набор тестов), но **основные “пробелы” лежат в enterprise-практиках**: OTel/трейсинг, централизованная observability-платформа, секрет-менеджмент, CI/CD + security scanning, кластеризация/оркестрация и формализованные тестовые практики (Hypothesis/testcontainers/mutation).
