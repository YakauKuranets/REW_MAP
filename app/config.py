"""
Модуль конфигурации приложения.

Здесь определяются классы конфигурации Flask с различными
параметрами для разработки и продакшена. Разделение конфигурации
позволяет хранить секреты и пути отдельно от кода, а также
упрощает переключение между окружениями.
"""

import os
import secrets
import warnings
from datetime import timedelta


def _safe_secret_key() -> str:
    """Получить SECRET_KEY из env или сгенерировать случайный.
    
    В продакшене ВСЕГДА задавайте SECRET_KEY через переменную окружения,
    иначе при перезапуске сервера все сессии инвалидируются.
    """
    key = os.environ.get("SECRET_KEY", "").strip()
    if not key:
        # Генерируем случайный ключ — сессии не будут переживать перезапуск,
        # но хотя бы не будет слабого захардкоженного ключа.
        key = secrets.token_hex(32)
        if os.environ.get("FLASK_ENV") != "development":
            warnings.warn(
                "SECRET_KEY не задан! Используется случайный ключ. "
                "Установите SECRET_KEY в переменных окружения для production.",
                RuntimeWarning,
                stacklevel=2,
            )
    return key


def _parse_int_set(env_name: str) -> set[int]:
    raw = (os.environ.get(env_name, "") or "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = (part or "").strip()
        if part.isdigit():
            out.add(int(part))
    return out

class Config:
    """Базовый класс конфигурации."""

    # Каталог, в котором размещается проект
    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    # База данных для зон: SQLite файл zones.db в корне проекта
    # Основная база данных. В ней хранятся не только зоны, но и адреса,
    # ожидающие заявки и история их обработки. Можно переопределить
    # через переменную окружения DATABASE_URI.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URI", f"sqlite:///{os.path.join(BASE_DIR, 'app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Секретный ключ — безопасная генерация (см. _safe_secret_key())
    SECRET_KEY = _safe_secret_key()

    # --- Cookie-сессии (админка) ---
    # Для безопасности: HttpOnly + SameSite. Secure включается в проде (HTTPS).
    SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "mapv12_session")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    # Время жизни "постоянной" сессии (используется после login, когда session.permanent=True)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_LIFETIME_HOURS", 12)))

    # JWT настройки
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or "hard-to-guess-secret-key-change-in-production"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # API Keys
    API_KEY_HEADER = os.environ.get("API_KEY_HEADER", "X-API-Key")
    API_KEY_EXPIRES_DAYS = int(os.environ.get("API_KEY_EXPIRES_DAYS", "365"))
    LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:11434/api/generate").strip()
    LLM_MODEL = os.environ.get("LLM_MODEL", "mistral").strip()

    # Пути к ML-моделям
    BERT_PASSWORD_MODEL = os.environ.get("BERT_PASSWORD_MODEL", "/models/password-bert")
    LEAK_CLASSIFIER_PATH = os.environ.get("LEAK_CLASSIFIER_PATH", "/models/leak-classifier")

    # Целевые объекты для мониторинга
    TARGET_EMAILS = os.environ.get("TARGET_EMAILS", "").split(",")
    TARGET_DOMAINS = os.environ.get("TARGET_DOMAINS", "").split(",")

    # SIEM настройки по умолчанию
    SIEM_EXPORT_BATCH_SIZE = os.environ.get("SIEM_EXPORT_BATCH_SIZE", 100)
    SIEM_RETRY_MAX_ATTEMPTS = os.environ.get("SIEM_RETRY_MAX_ATTEMPTS", 3)
    SIEM_CLEANUP_DAYS = os.environ.get("SIEM_CLEANUP_DAYS", 30)

    SHODAN_API_KEY = os.environ.get("SHODAN_API_KEY", "").strip()
    CENSYS_API_ID = os.environ.get("CENSYS_API_ID", "").strip()
    CENSYS_SECRET = os.environ.get("CENSYS_SECRET", "").strip()

    # Директория для загрузки фотографий. Она должна существовать,
    # иначе изображения не будут сохраняться. См. app/extensions.py
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    HANDSHAKE_UPLOAD_FOLDER = os.environ.get("HANDSHAKE_UPLOAD_FOLDER", "/data/handshakes")
    HASHCAT_WORDLIST = os.environ.get("HASHCAT_WORDLIST", "/data/wordlists/rockyou_optimized.txt")

    # --- AI feedback optimization (diagnostics quality improvement) ---
    AI_FEEDBACK_DATASET_PATH = os.environ.get("AI_FEEDBACK_DATASET_PATH", "/data/ai/diagnostics_feedback.jsonl").strip()
    AI_FINETUNE_SCRIPT = os.environ.get("AI_FINETUNE_SCRIPT", "/opt/ai/finetune_llm.py").strip()
    HANDSHAKE_MAX_FILE_SIZE_BYTES = int(os.environ.get("HANDSHAKE_MAX_FILE_SIZE_BYTES", str(10 * 1024 * 1024)))
    # Допустимые расширения файлов изображений
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

    # Учётные данные администратора. Имя пользователя и хеш пароля
    # задаются через переменные окружения; если передан только пароль,
    # он будет автоматически захеширован при старте приложения.
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    if os.environ.get("ADMIN_PASSWORD_HASH"):
        ADMIN_PASSWORD_HASH = os.environ["ADMIN_PASSWORD_HASH"]
    else:
        from werkzeug.security import generate_password_hash

        _plain_pw = os.environ.get("ADMIN_PASSWORD", "secret")
        ADMIN_PASSWORD_HASH = generate_password_hash(_plain_pw)

    # Пути к файлам с адресами и ожидающими заявками. Эти файлы
    # используются для простого хранения данных без базы (JSON).
    ADDRESS_FILE = os.path.join(BASE_DIR, "addresses.json")
    PENDING_FILE = os.path.join(BASE_DIR, "pending_markers.json")
    PENDING_HISTORY_FILE = os.path.join(BASE_DIR, "pending_history.json")

    # Путь к файлу офлайн-геокодирования и офлайн-карте
    OFFLINE_GEOCODE_FILE = os.path.join(BASE_DIR, "data", "offline", "geocode.json")
    DOWNLOAD_TILES_DIR = os.path.join(BASE_DIR, "data", "tiles_download")
    TILES_SETS_DIR = os.path.join(BASE_DIR, "data", "tiles_sets")
    ACTIVE_TILES_FILE = os.path.join(BASE_DIR, "data", "tiles_active_set.txt")

    # Настройки логирования. Можно переопределить через переменные окружения
    # LOG_LEVEL и LOG_FILE. По умолчанию уровень INFO и вывод только в консоль.
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE")  # если не задан, лог пишется только в stdout

    # Кэширование статики и тяжёлых API-эндпоинтов
    # Таймаут кэша для статики (по умолчанию 30 дней в проде, 0 в dev)
    STATIC_CACHE_TIMEOUT = int(os.environ.get("STATIC_CACHE_TIMEOUT", 0))
    # Таймаут кэша для аналитики (секунды)
    ANALYTICS_CACHE_SECONDS = int(os.environ.get("ANALYTICS_CACHE_SECONDS", 60))
    # Таймаут кэша для результатов геокодера (секунды)
    GEOCODE_CACHE_SECONDS = int(os.environ.get("GEOCODE_CACHE_SECONDS", 600))

    # --- Realtime (WebSocket / SSE) ---
    # Порт отдельного WS-сервера (dev/legacy режим). В проде рекомендуем ASGI-вариант (/ws на том же порту).
    WS_PORT = int(os.environ.get("WS_PORT", 8765))
    REALTIME_DISABLE_SAMEPORT = os.environ.get('REALTIME_DISABLE_SAMEPORT', '1')  # 1=не пытаться /ws на том же порту Flask
    # TTL токена (секунды) для подключения к realtime.
    REALTIME_TOKEN_TTL_SEC = int(os.environ.get("REALTIME_TOKEN_TTL_SEC", 600))
    # Разрешённые Origin'ы для WS (через запятую). Если пусто — разрешаем same-site и Origin=None (CLI).
    REALTIME_ALLOWED_ORIGINS = os.environ.get("REALTIME_ALLOWED_ORIGINS", "").strip()
    # --- Redis (опционально) ---
    # Используется для:
    #  - Pub/Sub для realtime (чтобы события доходили до всех воркеров/реплик)
    #  - Дистрибутивного lock для scheduler worker (чтобы не было двойного запуска)
    REDIS_URL = os.environ.get("REDIS_URL", "").strip()
    REALTIME_REDIS_CHANNEL = os.environ.get("REALTIME_REDIS_CHANNEL", "mapv12:realtime").strip()


    # --- MAX indoor / hysteresis tuning (field calibration) ---
    # Display-point hysteresis (GNSS ↔ estimate)
    DISPLAY_EST_FRESH_SEC = int(os.environ.get("DISPLAY_EST_FRESH_SEC", 120))
    DISPLAY_GNSS_STABLE_WINDOW_SEC = int(os.environ.get("DISPLAY_GNSS_STABLE_WINDOW_SEC", 25))
    DISPLAY_GNSS_STABLE_DIST_M = float(os.environ.get("DISPLAY_GNSS_STABLE_DIST_M", 50))
    DISPLAY_GOOD_GNSS_MAX_ACC_M = float(os.environ.get("DISPLAY_GOOD_GNSS_MAX_ACC_M", 60))

    # MAX anchors (localize_by_fingerprint)
    MAX_ANCHOR_MIN_WIFI_MATCHES = int(os.environ.get("MAX_ANCHOR_MIN_WIFI_MATCHES", 3))
    MAX_ANCHOR_MIN_SCORE = float(os.environ.get("MAX_ANCHOR_MIN_SCORE", 0.55))
    MAX_ANCHOR_MAX_GNSS_ACC_M = float(os.environ.get("MAX_ANCHOR_MAX_GNSS_ACC_M", 80))
    MAX_EST_THROTTLE_SEC = int(os.environ.get("MAX_EST_THROTTLE_SEC", 30))

    # Radio-map
    RADIO_MIN_SCORE = float(os.environ.get("RADIO_MIN_SCORE", 0.45))
    RADIO_MIN_WIFI_MATCHES = int(os.environ.get("RADIO_MIN_WIFI_MATCHES", 3))
    RADIO_MIN_CELL_MATCHES = int(os.environ.get("RADIO_MIN_CELL_MATCHES", 2))


    # --- Device status (Duty / Admin) ---
    # Единая логика статуса устройства в командном центре:
    #   - "В эфире"   : есть обновления совсем недавно (точка или heartbeat)
    #   - "Нет связи" : обновления были, но давно (например 2-10 минут)
    #   - "Не в сети" : обновлений нет совсем давно
    # Пороги можно крутить без правки кода через env.
    DEVICE_STATUS_ON_AIR_SEC = int(os.environ.get("DEVICE_STATUS_ON_AIR_SEC", 90))
    DEVICE_STATUS_NO_SIGNAL_SEC = int(os.environ.get("DEVICE_STATUS_NO_SIGNAL_SEC", 600))


    # --- Bot-to-server API key (optional) ---
    # Если задан, bot.py должен отправлять заголовок X-API-KEY.
    BOT_API_KEY = os.environ.get("BOT_API_KEY", "").strip()

    # Telegram bot token (для server-side авто-уведомлений, например авто-отправка кнопки DutyTracker)
    # Фолбэк: если TELEGRAM_BOT_TOKEN не задан, используем MAP_BOT_TOKEN / BOT_TOKEN (как в bot.py)
    TELEGRAM_BOT_TOKEN = (
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        or os.environ.get("MAP_BOT_TOKEN", "").strip()
        or os.environ.get("BOT_TOKEN", "").strip()
    )
    TELEGRAM_PROXY = os.environ.get("TELEGRAM_PROXY", "").strip()

    # Авто-отправка ссылки подключения DutyTracker при approve (если TELEGRAM_BOT_TOKEN задан)
    MOBILE_CONNECT_AUTO_SEND = os.environ.get("MOBILE_CONNECT_AUTO_SEND", "1") == "1"

    # Предпочтительный base_url для bootstrap (если задан, будет использоваться вместо авто-определения LAN IP)
    BOOTSTRAP_PREFERRED_BASE_URL = os.environ.get("BOOTSTRAP_PREFERRED_BASE_URL", "").strip()

    # --- Telegram allow-lists (optional) ---
    # Список Telegram user_id (через запятую), которым разрешены bootstrap-операции (выдача конфига для Android).
    # Если BOOTSTRAP_ALLOWED_TELEGRAM_IDS пуст, используем ADMIN_TELEGRAM_IDS.
    ADMIN_TELEGRAM_IDS = _parse_int_set("ADMIN_TELEGRAM_IDS")
    BOOTSTRAP_ALLOWED_TELEGRAM_IDS = _parse_int_set("BOOTSTRAP_ALLOWED_TELEGRAM_IDS")

    # TTL для bootstrap токена (в минутах)
    BOOTSTRAP_TTL_MIN = int(os.environ.get("BOOTSTRAP_TTL_MIN", "10"))

    # --- Tracker → Telegram notifications (optional) ---
    # Если TELEGRAM_BOT_TOKEN + ADMIN_TELEGRAM_IDS заданы, сервер может слать уведомления по CRIT алёртам.
    # 0/1
    TRACKER_TG_ALERT_NOTIFY = os.environ.get('TRACKER_TG_ALERT_NOTIFY', '1')
    # CSV: crit,warn,info (по умолчанию только crit)
    TRACKER_TG_NOTIFY_SEVERITIES = os.environ.get('TRACKER_TG_NOTIFY_SEVERITIES', 'crit')
    # CSV: если задано — шлём только по указанным kind (например 'tracking_off,app_error')
    TRACKER_TG_NOTIFY_KINDS = os.environ.get('TRACKER_TG_NOTIFY_KINDS', '')
    # Троттлинг: минимальный интервал между одинаковыми уведомлениями по device+kind, сек
    TRACKER_TG_NOTIFY_MIN_INTERVAL_SEC = int(os.environ.get('TRACKER_TG_NOTIFY_MIN_INTERVAL_SEC', '900'))

    # --- Devices / pairing behavior ---
    # Опционально: при новой привязке (pair) на тот же user_id автоматически
    # помечать старые устройства как revoked, чтобы у сотрудника оставалось
    # одно актуальное устройство и не было путаницы в /admin/devices.
    AUTO_REVOKE_ON_PAIR = (os.environ.get('AUTO_REVOKE_ON_PAIR', '1') or '1').strip().lower() in {'1','true','yes','y'}

    # --- Metrics (optional) ---
    ENABLE_METRICS = os.environ.get("ENABLE_METRICS", "0") == "1"
    METRICS_PATH = (os.environ.get("METRICS_PATH", "/metrics") or "/metrics").strip()
    METRICS_ALLOW_PUBLIC = os.environ.get("METRICS_ALLOW_PUBLIC", "0") == "1"
    # Если задан ключ - можно безопасно открыть /metrics наружу (Prometheus) без allow_public.
    METRICS_API_KEY = os.environ.get("METRICS_API_KEY", "").strip()

    # --- Rate limits ---
    RATE_LIMIT_LOGIN_PER_MINUTE = int(os.environ.get("RATE_LIMIT_LOGIN_PER_MINUTE", "10"))
    RATE_LIMIT_CHAT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_CHAT_PER_MINUTE", "120"))

    # Tracker (Android) – protects /api/tracker/* from accidental storms.
    # These limits are per-device (device.public_id).
    RATE_LIMIT_TRACKER_POINTS_PER_MINUTE = int(os.environ.get("RATE_LIMIT_TRACKER_POINTS_PER_MINUTE", "6000"))
    RATE_LIMIT_TRACKER_FINGERPRINTS_PER_MINUTE = int(os.environ.get("RATE_LIMIT_TRACKER_FINGERPRINTS_PER_MINUTE", "60"))
    RATE_LIMIT_TRACKER_HEALTH_PER_MINUTE = int(os.environ.get("RATE_LIMIT_TRACKER_HEALTH_PER_MINUTE", "120"))
    # SOS is intentionally low; window is 5 minutes in code.
    RATE_LIMIT_TRACKER_SOS_PER_5MIN = int(os.environ.get("RATE_LIMIT_TRACKER_SOS_PER_5MIN", "3"))

    # Admin API writes (objects/incidents). Per-admin (session) or per-IP fallback.
    RATE_LIMIT_OBJECTS_WRITE_PER_MINUTE = int(os.environ.get("RATE_LIMIT_OBJECTS_WRITE_PER_MINUTE", "120"))
    RATE_LIMIT_INCIDENTS_WRITE_PER_MINUTE = int(os.environ.get("RATE_LIMIT_INCIDENTS_WRITE_PER_MINUTE", "180"))
    RATE_LIMIT_OBJECTS_IMPORT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_OBJECTS_IMPORT_PER_MINUTE", "10"))

    # Chat2 rate limits (unified knobs; keep backward compatible names)
    CHAT2_SEND_RATE_WINDOW_SEC = float(os.environ.get("CHAT2_SEND_RATE_WINDOW_SEC", "60"))
    CHAT2_SEND_RATE_LIMIT = int(os.environ.get("CHAT2_SEND_RATE_LIMIT", str(RATE_LIMIT_CHAT_PER_MINUTE)))
    CHAT2_UPLOAD_RATE_WINDOW_SEC = float(os.environ.get("CHAT2_UPLOAD_RATE_WINDOW_SEC", "60"))
    CHAT2_UPLOAD_RATE_LIMIT = int(os.environ.get("CHAT2_UPLOAD_RATE_LIMIT", os.environ.get("RATE_LIMIT_MEDIA_UPLOAD_PER_MINUTE", "20")))

    # --- Retention / cleanup (best-effort, opt-in) ---
    # Tracks (GNSS/indoor points) are the largest dataset.
    RETENTION_TRACK_DAYS = int(os.environ.get("RETENTION_TRACK_DAYS", "30"))
    # Chats (event-log based) usually keep a bit longer.
    RETENTION_CHAT_DAYS = int(os.environ.get("RETENTION_CHAT_DAYS", "90"))
    # Incidents and related timelines/assignments – longer by default.
    RETENTION_INCIDENTS_DAYS = int(os.environ.get("RETENTION_INCIDENTS_DAYS", "180"))
    # Safety: delete only resolved/closed incidents unless explicitly disabled.
    RETENTION_DELETE_ONLY_CLOSED = (os.environ.get("RETENTION_DELETE_ONLY_CLOSED", "1") or "1").strip().lower() in {"1","true","yes","y"}
    # If enabled, run cleanup once on app start (not recommended for multi-worker prod).
    RETENTION_RUN_ON_STARTUP = os.environ.get("RETENTION_RUN_ON_STARTUP", "0") == "1"

    # Optional scheduler for retention cleanup (best-effort).
    # NOTE: In production with multiple web workers, prefer running schedulers
    # in a separate worker container/process.
    RETENTION_SCHEDULER_ENABLED = os.environ.get("RETENTION_SCHEDULER_ENABLED", "0") == "1"
    RETENTION_SCHEDULER_EVERY_MINUTES = int(os.environ.get("RETENTION_SCHEDULER_EVERY_MINUTES", "360"))
    # Start delay to avoid running immediately after boot (seconds)
    RETENTION_SCHEDULER_START_DELAY_SEC = int(os.environ.get("RETENTION_SCHEDULER_START_DELAY_SEC", "30"))
    # Best-effort Redis lock to prevent duplicate runs in multi-worker setups
    RETENTION_SCHEDULER_LOCK_KEY = os.environ.get("RETENTION_SCHEDULER_LOCK_KEY", "mapv12:retention:lock")
    RETENTION_SCHEDULER_LOCK_TTL_SEC = int(os.environ.get("RETENTION_SCHEDULER_LOCK_TTL_SEC", "600"))

    TELEGRAM_ALERT_CHAT_ID = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "").strip()

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "").strip()
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "").strip()
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "").strip()
    MAIL_USE_TLS = (os.environ.get("MAIL_USE_TLS", "1") or "1").strip().lower() in {"1", "true", "yes", "y"}

    # Bot API (Telegram) rate limits (best-effort)
    RATE_LIMIT_BOT_MARKERS_PER_MINUTE = int(os.environ.get("RATE_LIMIT_BOT_MARKERS_PER_MINUTE", "60"))
    RATE_LIMIT_BOT_STATUS_PER_MINUTE = int(os.environ.get("RATE_LIMIT_BOT_STATUS_PER_MINUTE", "180"))
    RATE_LIMIT_BOT_CANCEL_PER_MINUTE = int(os.environ.get("RATE_LIMIT_BOT_CANCEL_PER_MINUTE", "60"))
    RATE_LIMIT_BOT_MYREQ_PER_MINUTE = int(os.environ.get("RATE_LIMIT_BOT_MYREQ_PER_MINUTE", "120"))

    # Duty bot endpoints (best-effort)
    RATE_LIMIT_DUTY_SHIFT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_DUTY_SHIFT_PER_MINUTE", "120"))
    RATE_LIMIT_DUTY_CHECKIN_PER_MINUTE = int(os.environ.get("RATE_LIMIT_DUTY_CHECKIN_PER_MINUTE", "240"))
    RATE_LIMIT_DUTY_LIVE_PER_MINUTE = int(os.environ.get("RATE_LIMIT_DUTY_LIVE_PER_MINUTE", "600"))
    RATE_LIMIT_DUTY_TRACKING_STOP_PER_MINUTE = int(os.environ.get("RATE_LIMIT_DUTY_TRACKING_STOP_PER_MINUTE", "60"))
    RATE_LIMIT_DUTY_SOS_PER_MINUTE = int(os.environ.get("RATE_LIMIT_DUTY_SOS_PER_MINUTE", "30"))
    RATE_LIMIT_DUTY_BREAK_PER_MINUTE = int(os.environ.get("RATE_LIMIT_DUTY_BREAK_PER_MINUTE", "60"))
    RATE_LIMIT_DUTY_SETUNIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_DUTY_SETUNIT_PER_MINUTE", "60"))

    # --- Celery (background workers) ---
    _default_redis = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", _default_redis)
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", _default_redis)

    CELERY_BEAT_SCHEDULE = {
        "scan-shodan-for-cameras-daily": {
            "task": "app.tasks.shodan_scanner.scan_shodan_for_cameras",
            "schedule": 86400.0,
            "kwargs": {
                "query": 'product:"Hikvision" OR product:"Dahua"',
                "limit": 100,
            },
        },
        "check-security-alerts": {
            "task": "app.alerting.checker.check_alerts",
            "schedule": float(os.environ.get("ALERT_CHECK_INTERVAL_SEC", "60")),
        },
    }
    # --- Schedulers (background worker) ---
    # Важно: в проде планировщики должны работать в отдельном worker-контейнере.
    ENABLE_INTERNAL_SCHEDULERS = os.environ.get("ENABLE_INTERNAL_SCHEDULERS", "0") == "1"
    SCHEDULER_LOCK_KEY = os.environ.get("SCHEDULER_LOCK_KEY", "mapv12:schedulers:lock")
    SCHEDULER_LOCK_TTL_SEC = int(os.environ.get("SCHEDULER_LOCK_TTL_SEC", 60))



class DevelopmentConfig(Config):
    """Настройки для режима разработки."""

    DEBUG = True
    ENABLE_INTERNAL_SCHEDULERS = os.environ.get("ENABLE_INTERNAL_SCHEDULERS", "1") == "1"
    # В разработке не кэшируем статику, чтобы правки были видны сразу
    SEND_FILE_MAX_AGE_DEFAULT = 0




class TestingConfig(Config):
    """Настройки для тестов."""

    TESTING = True
    DEBUG = True
    # В тестах планировщики не запускаем автоматически.
    ENABLE_INTERNAL_SCHEDULERS = False
    # Не кэшируем статику, чтобы снапшоты/тесты были предсказуемыми
    SEND_FILE_MAX_AGE_DEFAULT = 0
class ProductionConfig(Config):
    # В продакшене по умолчанию считаем, что есть HTTPS.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "1") == "1"
    """Настройки для режима продакшена."""

    DEBUG = False
    ENABLE_INTERNAL_SCHEDULERS = os.environ.get("ENABLE_INTERNAL_SCHEDULERS", "0") == "1"
    # В продакшене можно кэшировать статику длительно (30 дней)
    from datetime import timedelta
    SEND_FILE_MAX_AGE_DEFAULT = timedelta(days=30)
