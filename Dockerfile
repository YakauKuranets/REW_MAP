# Dockerfile для проекта Map v12 + Telegram-бот
#
# Использование (локальная разработка):
#   docker build -t mapv12 .
#   docker compose -f docker-compose.dev.yml up
#
# Для прод-окружения будет использоваться docker-compose.prod.yml.

FROM python:3.11-slim

# Устанавливаем системные зависимости (по минимуму)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Рабочий каталог внутри контейнера
WORKDIR /app

# Копируем файлы зависимостей и устанавливаем их
COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код приложения
COPY . /app

# entrypoint scripts
RUN chmod +x deploy/entrypoint_web.sh || true

# По умолчанию запускаем gunicorn с конфигом из deploy/
# Для сервиса бота команда будет переопределена в docker-compose.
CMD ["gunicorn", "-c", "deploy/gunicorn.conf.py", "wsgi:app"]
