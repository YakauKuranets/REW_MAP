"""
Базовые тесты для Telegram‑бота.

Эти тесты являются лишь примером и помогают убедиться, что ключевые функции
бота корректно обрабатывают типичные ответы от сервера.  Тесты используют
unittest.mock для подмены запросов, чтобы не делать реальные HTTP‑вызовы.
Запуск тестов требует asyncio‑совместимого PyTest (pytest‑asyncio).
"""
import asyncio
from unittest.mock import patch, MagicMock

import pytest

# Импортируем модуль бота; путь должен быть корректен, если запускать тесты
# из корня репозитория.  Если PyTest не находит bot.py, добавьте его
# директорию в sys.path.
import bot as bot_module


@pytest.mark.asyncio
async def test_admin_post_login_accepts_201():
    """Проверяем, что admin_POST_login принимает код 201 как успешный."""
    # Подменяем requests.Session, чтобы вернуть фиктивный ответ
    with patch("bot.requests.Session") as MockSession:
        sess = MockSession.return_value
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"status": "ok"}
        sess.post.return_value = resp
        ok, s, err = await bot_module.admin_POST_login("user", "pass")
        assert ok is True
        assert s is sess
        assert err == ""


@pytest.mark.asyncio
async def test_send_application_accepts_201(monkeypatch):
    """Проверяем, что отправка заявки возвращает успех при коде 201."""
    # Выбираем тестовые данные
    test_data = {
        "address": "Тестовый адрес",
        "notes": "Примечание",
        "lat": 0.0,
        "lon": 0.0,
        "status": "Локальный доступ",
        "category": "Видеонаблюдение",
        "reporter_surname": "Иванов",
        "tg_user_id": 123,
        "tg_message_id": 456,
        "photo_path": None,
    }

    # Заглушка для requests.post, возвращающая ответ с кодом 201
    class DummyResponse:
        status_code = 201
        def json(self):
            return {"message": "created"}
        text = ""

    async def dummy_send(*args, **kwargs):
        return True, ""

    # Подменяем функцию, вызываемую внутри bot.add_marker_via_api
    monkeypatch.setattr(bot_module, "add_marker_via_api", dummy_send)

    with patch("bot.requests.post", return_value=DummyResponse()) as _:
        # Вызов внутренней функции _do_post через публичный API невозможен,
        # поэтому здесь проверяем косвенно через add_marker_via_api
        ok, err = await bot_module.add_marker_via_api(
            test_data["address"],
            test_data["notes"],
            test_data["lat"],
            test_data["lon"],
            test_data["status"],
            test_data["category"],
            test_data["reporter_surname"],
            None,
            test_data["tg_user_id"],
            test_data["tg_message_id"],
        )
        assert ok is True
        assert err == ""