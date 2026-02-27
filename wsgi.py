"""WSGI-энтрипоинт для прод-окружения.

Используется такими серверами, как gunicorn или uWSGI:
    gunicorn wsgi:app

Здесь мы создаём Flask-приложение с прод-конфигурацией.
"""

import os

from env_loader import load_dotenv_like

# Load .env if present
load_dotenv_like()

from app import create_app
from app.config import ProductionConfig


# Можно переопределить класс конфигурации через переменную окружения,
# если захочется, но по умолчанию используем ProductionConfig.
def get_config_class():
    cfg_name = os.environ.get("APP_CONFIG", "production").lower()
    if cfg_name in {"prod", "production"}:
        return ProductionConfig
    # на всякий случай оставляем возможность подхватить dev/config
    from app.config import DevelopmentConfig, TestingConfig
    if cfg_name in {"dev", "development"}:
        return DevelopmentConfig
    if cfg_name in {"test", "testing"}:
        return TestingConfig
    return ProductionConfig


app = create_app(get_config_class())


if __name__ == "__main__":
    # Небольшой запуск для локальной проверки WSGI-энтрипоинта
    # В реальном проде использовать gunicorn/uwsgi.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
