# Точка входа ДЛЯ РАЗРАБОТКИ (debug server)
# В продакшене использовать wsgi.py/asgi.py + gunicorn/uvicorn.

"""Точка входа для запуска Flask‑приложения.

Выполните этот файл, чтобы запустить сервер разработки или
простое прод‑окружение. Конфигурация выбирается автоматически
на основе переменной окружения:

- ``APP_ENV=production`` или ``FLASK_ENV=production`` → ProductionConfig
- во всех остальных случаях используется DevelopmentConfig.
"""

import logging
import os

from env_loader import load_dotenv_like

# Load .env if present (so запуск из PyCharm подхватывал конфиг)
load_dotenv_like()
from threading import Thread

from app import create_app
from app.config import DevelopmentConfig, ProductionConfig
from app.sockets import start_socket_server


def _select_config_class() -> type:
    """Выбрать класс конфигурации в зависимости от окружения.

    Приоритет имеет переменная ``APP_ENV`` (production / development),
    затем ``FLASK_ENV``. Любое значение, начинающееся с ``prod``,
    приводит к выбору :class:`ProductionConfig`.
    """
    env = (os.getenv('APP_ENV') or os.getenv('FLASK_ENV') or 'development').lower()
    if env.startswith('prod'):
        return ProductionConfig
    return DevelopmentConfig


def main() -> None:
    """Запуск веб‑сервера и, при необходимости, WebSocket‑сервера.

    В режиме отладки Flask использует два процесса: родительский для
    отслеживания изменений и дочерний для обслуживания запросов.
    Чтобы предотвратить попытку повторного запуска WebSocket‑сервера,
    проверяем переменную окружения ``WERKZEUG_RUN_MAIN`` – она
    устанавливается во ``true`` только в рабочем процессе. В продакшене
    (debug=False) проверка также проходит, и сервер запускается один раз.
    """
    # Создаём Flask‑приложение перед запуском фоновых сервисов, чтобы иметь
    # доступ к конфигурации (например, app.debug) и избежать двойного запуска
    config_class = _select_config_class()
    app = create_app(config_class)

    # Запускаем WebSocket‑сервер только в основном процессе, чтобы избежать
    # ошибки "address already in use" при перезапуске отладочного сервера.
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            ws_thread = Thread(
                target=start_socket_server,
                args=('0.0.0.0', int(app.config.get('WS_PORT', 8765))),
                kwargs={
                    'secret_key': app.secret_key,
                    'token_ttl': int(app.config.get('REALTIME_TOKEN_TTL_SEC', 600)),
                    'allowed_origins': str(app.config.get('REALTIME_ALLOWED_ORIGINS', '')),
                },
                daemon=True,
            )
            ws_thread.start()
        except OSError as e:
            # Если порт уже занят, выводим предупреждение и продолжаем запуск
            logging.getLogger(__name__).warning(
                'Не удалось запустить WebSocket‑сервер: %s', e
            )

    # Запускаем встроенный веб‑сервер
    # В продакшене используйте полноценный WSGI‑сервер (uWSGI, gunicorn и т.д.).
    app.run(host='0.0.0.0', port=5000, debug=app.config.get('DEBUG', True))


if __name__ == '__main__':
    main()
